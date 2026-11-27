"""Explainable SQL recommendations, group matching and scoped merchant analytics."""
from datetime import datetime, timedelta
import json
import math

from database import operations
from . import service


def ranked_stores(connection, user_id, where, parameters, limit, offset):
    # Each signal contributes at most once per store and source. Repeated
    # purchases cannot overwhelm favorites or positive reviews.
    sql = '''WITH activity AS (
        SELECT store_id, 3 AS weight FROM favorites WHERE user_id=?
        UNION ALL SELECT store_id, 2 FROM reviews WHERE user_id=? AND rating>=4
        UNION ALL SELECT DISTINCT c.store_id, 2 FROM orders o
          JOIN coupons c ON c.coupon_id=o.coupon_id WHERE o.user_id=?
    ), history AS (
        SELECT s.category_id,s.district_id,a.weight FROM activity a JOIN stores s USING(store_id)
    ), context AS (SELECT coalesce(sum(weight),0) AS total FROM history),
    category_weights AS (SELECT category_id,sum(weight) AS weight FROM history GROUP BY category_id),
    district_weights AS (SELECT district_id,sum(weight) AS weight FROM history GROUP BY district_id),
    candidate AS (''' + service.STORE_SELECT + service.STORE_FROM + where + '''),
    features AS (
        SELECT candidate.*,
          coalesce(cw.weight*1.0/nullif(context.total,0),0) AS interest,
          coalesce(dw.weight*1.0/nullif(context.total,0),0) AS affinity,
          (coalesce(average_rating,3.5)*review_count+17.5)/(review_count+5)/5.0 AS reputation,
          coalesce((SELECT max(1.0-c.price_cents*1.0/nullif(c.original_price_cents,0))
            FROM coupons c WHERE c.store_id=candidate.store_id AND c.is_active=1
              AND c.available_stock>0 AND c.expires_on>=date('now','+8 hours')),0) AS value_score,
          context.total AS evidence
        FROM candidate CROSS JOIN context
        LEFT JOIN category_weights cw USING(category_id)
        LEFT JOIN district_weights dw USING(district_id)
    ), scored AS (
        SELECT features.*, round(100*CASE WHEN evidence>0 THEN
          .35*interest+.25*reputation+.20*affinity+.20*value_score
          ELSE .65*reputation+.35*value_score END,2) AS recommendation_score
        FROM features
    ) SELECT * FROM scored ORDER BY recommendation_score DESC,store_id LIMIT ? OFFSET ?'''
    return connection.execute(sql,[user_id]*4+parameters+[limit,offset]).fetchall()


def recommendation(row):
    reasons = []
    if row['interest'] > 0:
        reasons.append('符合你的餐饮类别偏好')
    if row['affinity'] > 0:
        reasons.append('符合你的常去地区偏好')
    if row['reputation'] >= .8:
        reasons.append('综合口碑较好')
    if row['value_score'] > 0:
        reasons.append('有有效折扣')
    if not reasons:
        reasons.append('根据点评与在售优惠排序')
    return {'score':row['recommendation_score'], 'personalized':bool(row['evidence']),
            'reasons':reasons, 'components':{k:round(row[k]*100,2) for k in
                ('interest','reputation','affinity','value_score')}}


def group_match(connection, session, query):
    """Temporary member preferences form a relational VALUES table.

    Budget is a hard constraint for all members; category is a soft preference.
    Rank by worst-member satisfaction, then mean, then stable ID. No names or
    persistent group data are required for a local shared planning session.
    """
    try:
        raw = service.query_value(query,'members')
        if len(raw)>3000:
            raise ValueError()
        members = json.loads(raw)
        if not isinstance(members,list) or not 2<=len(members)<=8:
            raise ValueError()
        for member in members:
            if (not isinstance(member,dict) or set(member)!={'budget','category'}
                    or type(member['budget']) is not int or not 1<=member['budget']<=10000
                    or not isinstance(member['category'],str) or len(member['category'])>80):
                raise ValueError()
    except (ValueError,TypeError):
        raise service.APIError(400,'INVALID_GROUP','请输入 2–8 位成员、1–10000 港元整数预算及有效类别。')
    district=service.query_value(query,'district')
    limit,offset=service.page_bounds(query,12)
    user_id=session['user_id'] if session else None
    with service.read_snapshot(connection):
        categories={r[0] for r in connection.execute('SELECT category_id FROM categories')}
        districts={r[0] for r in connection.execute('SELECT district_id FROM districts')}
        if any(m['category'] and m['category'] not in categories for m in members) or (district and district not in districts):
            raise service.APIError(400,'INVALID_GROUP','请选择有效的餐饮类别与聚餐地区。')
        values=','.join('(?,?,?)' for _ in members)
        params=[v for i,m in enumerate(members,1) for v in (i,m['budget']*100,m['category'])]
        eligible='WHERE s.is_active=1 AND (?=\'\' OR s.district_id=?) AND s.price_per_person_cents <= (SELECT min(budget) FROM members)'
        prefix='WITH members(member_no,budget,category) AS (VALUES '+values+'), candidate AS ('+service.STORE_SELECT+service.STORE_FROM+eligible+'''),
          pairs AS (SELECT c.store_id,m.member_no,
            CASE WHEN m.category='' OR m.category=c.category_id THEN 1 ELSE 0 END AS matched,
            100*(.65*(CASE WHEN m.category='' OR m.category=c.category_id THEN 1 ELSE 0 END)
                + .25*(coalesce(c.average_rating,3.5)*c.review_count+17.5)/(c.review_count+5)/5.0
                + .10*(1.0-c.price_per_person_cents*1.0/m.budget)) AS satisfaction
            FROM candidate c CROSS JOIN members m),
          consensus AS (SELECT store_id,min(satisfaction) AS worst_score,avg(satisfaction) AS mean_score,
            sum(matched) AS matched_members FROM pairs GROUP BY store_id)
          '''
        bound=params+[user_id,district,district]
        total=connection.execute(prefix+'SELECT count(*) FROM consensus',bound).fetchone()[0]
        rows=connection.execute(prefix+'''SELECT candidate.*,consensus.worst_score,consensus.mean_score,consensus.matched_members
          FROM candidate JOIN consensus USING(store_id) ORDER BY worst_score DESC,mean_score DESC,store_id
          LIMIT ? OFFSET ?''',bound+[limit,offset]).fetchall()
        items=[]
        for row in rows:
            store=service.store_object(connection,row)
            store['groupMatch']={'matchedMembers':row['matched_members'],'memberCount':len(members),
                'worstScore':round(row['worst_score'],1),'meanScore':round(row['mean_score'],1),
                'budgetLimit':min(m['budget'] for m in members)}
            items.append(store)
        return service.page_result(items,total,limit,offset,memberCount=len(members),
            budgetLimit=min(m['budget'] for m in members))


def merchant_analytics(connection, session, query):
    user_id=service.require_session(session)
    days=int(service.enum_value(query,'days',('7','30'),'7'))
    store_id=service.query_value(query,'storeId')
    # Scope every query to one authorized branch; don't expose buyer records.
    with service.read_snapshot(connection):
        allowed=service.staff_stores(connection,user_id)
        if not allowed or not store_id or store_id not in allowed:
            raise service.APIError(403,'FORBIDDEN','你没有这家门店的经营分析权限。')
        today=datetime.now(operations.HK).date()
        start=today-timedelta(days=days-1)
        start_epoch=int(datetime.combine(start,datetime.min.time(),operations.HK).timestamp())
        end_epoch=int(datetime.combine(today+timedelta(days=1),datetime.min.time(),operations.HK).timestamp())
        scope=''' FROM orders o JOIN coupons c ON c.coupon_id=o.coupon_id
          LEFT JOIN redemptions r ON r.order_id=o.order_id
          WHERE c.store_id=? AND o.purchased_at>=? AND o.purchased_at<?'''
        bound=(store_id,start_epoch,end_epoch)
        totals=connection.execute('''SELECT count(*) AS sold,coalesce(sum(o.price_paid_cents),0) AS gross,
          count(r.order_id) AS redeemed,
          coalesce(sum(CASE WHEN r.order_id IS NULL AND o.expires_on_snapshot<? THEN 1 ELSE 0 END),0) AS expired'''+scope,
          (today.isoformat(),)+bound).fetchone()
        today_epoch=int(datetime.combine(today,datetime.min.time(),operations.HK).timestamp())
        today_row=connection.execute('SELECT count(*),coalesce(sum(o.price_paid_cents),0)'+scope,
            (store_id,today_epoch,end_epoch)).fetchone()
        trend=connection.execute('''WITH RECURSIVE calendar(day) AS (
          SELECT ? UNION ALL SELECT date(day,'+1 day') FROM calendar WHERE day<?),
          daily AS (SELECT date(o.purchased_at,'unixepoch','+8 hours') AS day,
             count(*) AS sold,sum(o.price_paid_cents) AS gross'''+scope+''' GROUP BY day)
          SELECT calendar.day,coalesce(daily.sold,0) AS sold,coalesce(daily.gross,0) AS gross,
             sum(coalesce(daily.gross,0)) OVER (ORDER BY calendar.day) AS cumulative
          FROM calendar LEFT JOIN daily USING(day) ORDER BY calendar.day''',
          (start.isoformat(),today.isoformat())+bound).fetchall()
        # Aggregate sales before joining inventory, so current stock is never
        # repeated by one-to-many order joins. Include unsold offers.
        offers=connection.execute('''WITH sales AS (SELECT o.coupon_id,count(*) AS sold,
          sum(o.price_paid_cents) AS gross,count(r.order_id) AS redeemed'''+scope+''' GROUP BY o.coupon_id),
          ranked AS (SELECT c.coupon_id,c.title,c.available_stock,c.is_active,c.expires_on,
            coalesce(s.sold,0) AS sold,coalesce(s.gross,0) AS gross,coalesce(s.redeemed,0) AS redeemed,
            dense_rank() OVER (ORDER BY coalesce(s.sold,0) DESC) AS rank
          FROM coupons c LEFT JOIN sales s USING(coupon_id) WHERE c.store_id=?)
          SELECT * FROM ranked ORDER BY rank,coupon_id LIMIT 50''',bound+(store_id,)).fetchall()
        branches=connection.execute('''WITH scoped AS (SELECT s.store_id,s.name FROM store_staff ss
          JOIN stores s USING(store_id) WHERE ss.user_id=? AND ss.is_active=1),
          sales AS (SELECT c.store_id,count(o.order_id) AS sold,sum(o.price_paid_cents) AS gross
          FROM scoped JOIN coupons c USING(store_id) JOIN orders o USING(coupon_id)
          WHERE o.purchased_at>=? AND o.purchased_at<? GROUP BY c.store_id)
          SELECT scoped.*,coalesce(sales.sold,0) AS sold,coalesce(sales.gross,0) AS gross,
          dense_rank() OVER (ORDER BY coalesce(sales.sold,0) DESC) AS rank
          FROM scoped LEFT JOIN sales USING(store_id) ORDER BY rank,store_id LIMIT 50''',
          (user_id,start_epoch,end_epoch)).fetchall()
        rating_rows=connection.execute('''SELECT date(created_at,'unixepoch','+8 hours') AS day,
          count(*) AS n,round(avg(rating),2) AS rating FROM reviews
          WHERE store_id=? AND created_at>=? AND created_at<? GROUP BY day ORDER BY day''',bound).fetchall()
        result=[]
        for row in offers:
            valid=bool(row['is_active'] and row['expires_on']>=today.isoformat())
            result.append({'id':row['coupon_id'],'title':row['title'],'rank':row['rank'],
                'sold':row['sold'],'gross':row['gross']/100,'redeemed':row['redeemed'],'stock':row['available_stock'],
                'lowStock':valid and row['available_stock']<=5,'active':valid,
                'suggestedRestock':max(0,math.ceil(3*row['sold']/days)-row['available_stock']) if valid else 0})
        can_adjust=bool(connection.execute("SELECT 1 FROM store_staff WHERE store_id=? AND user_id=? AND is_active=1 AND role IN ('owner','manager')",(store_id,user_id)).fetchone())
        return {'storeId':store_id,'days':days,'start':start.isoformat(),'end':today.isoformat(),'canAdjustStock':can_adjust,
            'sold':totals['sold'],'gross':totals['gross']/100,'redeemed':totals['redeemed'],
            'expired':totals['expired'],'unused':totals['sold']-totals['redeemed']-totals['expired'],
            'redemptionRate':round(totals['redeemed']*100/totals['sold'],1) if totals['sold'] else None,
            'todaySold':today_row[0],'todayGross':today_row[1]/100,
            'trend':[{'day':r['day'],'sold':r['sold'],'gross':r['gross']/100,'cumulative':r['cumulative']/100} for r in trend],
            'offers':result,
            'branches':[{'id':r['store_id'],'name':r['name'],'sold':r['sold'],'gross':r['gross']/100,'rank':r['rank']} for r in branches],
            'ratingTrend':[{'day':r['day'],'count':r['n'],'average':r['rating']} for r in rating_rows]}
