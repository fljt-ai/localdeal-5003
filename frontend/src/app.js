// LocalDeal: server-filtered pages, bounded identity caches and session cookies.
(() => {
  'use strict';
  const API = window.LocalDealAPI;
  const i18n=window.LocalDealI18n || {t:s=>String(s??''),language:'zh-CN',set(){}};
  const t=s=>i18n.t(s);
  const userEsc=s=>esc(s).replace(/[\u3000-\u303f\u3400-\u9fff\uff00-\uffef]/g,c=>`&#${c.charCodeAt(0)};`);
  const $ = (selector, parent = document) => parent.querySelector(selector);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const money = n => `HK$${Number(n).toFixed(Number(n) % 1 ? 2 : 0)}`;
  const dateText = d => d ? new Date(/^\d{4}-\d{2}-\d{2}$/.test(d) ? `${d}T12:00:00` : d).toLocaleDateString(i18n.language, {month:'2-digit',day:'2-digit'}) : '—';
  const paths = {
    compass:'<circle cx="12" cy="12" r="9"/><path d="m16 8-3 5-5 3 3-5z"/>',
    ticket:'<path d="M4 5h16v4a3 3 0 0 0 0 6v4H4v-4a3 3 0 0 0 0-6z"/><path d="M15 5v3m0 3v2m0 3v3"/>',
    wallet:'<path d="M4 6h15v4H4a2 2 0 0 1 0-4Zm0 4v9h17V9h-5v6h5"/><path d="M17 12h1"/>',
    user:'<circle cx="12" cy="8" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/>',
    store:'<path d="m3 9 2-6h14l2 6M3 9c0 4 6 4 6 0 0 4 6 4 6 0 0 4 6 4 6 0M5 12v9h14v-9M9 21v-6h6v6"/>',
    pin:'<path d="M19 10c0 5-7 11-7 11S5 15 5 10a7 7 0 0 1 14 0Z"/><circle cx="12" cy="10" r="2"/>',
    search:'<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
    heart:'<path d="M20 5a5.5 5.5 0 0 0-8 1 5.5 5.5 0 0 0-8-1c-3 3-1 7 2 10l6 6 6-6c3-3 5-7 2-10Z"/>',
    star:'<path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2-5.6-3-5.6 3 1.1-6.2L3 9.6l6.2-.9z"/>',
    clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    back:'<path d="m14 5-7 7 7 7"/>', close:'<path d="m6 6 12 12M6 18 18 6"/>',
    check:'<path d="m5 12 4 4L19 6"/>',
    coffee:'<path d="M4 8h12v6a6 6 0 0 1-12 0zM16 8h2a3 3 0 0 1 0 6h-2M3 21h15M7 2v3m5-3v3"/>',
    food:'<path d="M4 3v6a3 3 0 0 0 6 0V3M7 3v18M4 7h6M19 21V3c-4 0-5 7-5 10h5"/>',
    grid:'<rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/>',
    copy:'<rect x="8" y="8" width="12" height="13" rx="2"/><path d="M16 8V3H3v13h5"/>',
    edit:'<path d="m16 3 5 5-12 12H4v-5zM13 6l5 5"/>',
    download:'<path d="M12 3v13m-5-5 5 5 5-5M4 17v4h16v-4"/>',
    refresh:'<path d="M20 8a8 8 0 0 0-14-3L3 8m0-5v5h5M4 16a8 8 0 0 0 14 3l3-3m0 5v-5h-5"/>',
    logout:'<path d="M9 3H4v18h5m5-14 5 5-5 5M9 12h10"/>',
    shield:'<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6z"/><path d="m8 12 3 3 5-6"/>'
  };
  const icon = (name, extra='') => `<svg class="icon ${extra}" viewBox="0 0 24 24" aria-hidden="true">${paths[name] || paths.grid}</svg>`;
  const initials = n => n?userEsc(Array.from(n)[0].toUpperCase()):t('访');
  const navs = [{id:'discover',name:'发现好店',icon:'compass'},{id:'group',name:'聚餐匹配',icon:'food'},{id:'deals',name:'精选优惠',icon:'ticket'},{id:'wallet',name:'我的券包',icon:'wallet'},{id:'profile',name:'个人中心',icon:'user'}];
  const emptyPage = limit => ({items:[],total:0,limit,offset:0,hasMore:false});
  const stores = new Map(), coupons = new Map(), reviews = new Map();
  const remember = (map, item, maximum=64) => {
    if (!item?.id) return;
    map.delete(item.id); map.set(item.id, item);
    while (map.size > maximum) map.delete(map.keys().next().value);
  };
  const rememberStore = s => { remember(stores,s); if(s?.coupon)remember(coupons,s.coupon); };
  let state, filters = {search:'',category:'',district:'',sort:'recommended',couponOnly:false};
  let walletTab='all', profileTab='favorites', reviewSort='new', reviewRating='all', merchantStatus='all';
  let merchantStore='', redemptionResult=null, route='discover', currentStore=null, modalRating=5, pending=false;
  let offset=0, page=emptyPage(12), sidebarFavorites=[], authorizedStores=[], detailStore=null, ownReview=null;
  let loading=false, pageError='', loadSerial=0, bootstrapSerial=0, modalSerial=0, searchTimer;
  let groupMembers=[{budget:'120',category:''},{budget:'120',category:''}], groupDistrict='', groupQuery=null;
  let analyticsDays='7', merchantAnalytics=null;
  const storeOf = id => stores.get(id);
  const couponOf = id => coupons.get(id);
  const summary = () => state?.summary || {favorites:0,reviews:0,orders:{all:0,unused:0,redeemed:0,expired:0}};
  const merchantIds = () => state?.user?.merchantStoreIds || [];
  const isMerchant = () => merchantIds().length > 0;
  const statusOf = o => API.getOrderStatus(o);
  const statusText = s => ({unused:'待使用',redeemed:'已核销',expired:'已过期'}[s] || s);
  const validCoupon = c => c?.isPurchasable === true;
  const scoreText = s => s?.averageRating == null ? '新店' : Number(s.averageRating).toFixed(1);
  const rating = s => `<span class="rating">${icon('star')}${scoreText(s)}</span>`;
  const stars = n => `<div class="stars" aria-label="${n} 星">${[1,2,3,4,5].map(i=>icon('star',i>n?'off':'')).join('')}</div>`;
  const favoriteButton = s => `<button class="favorite ${s.isFavorite?'active':''}" data-action="favorite" data-id="${esc(s.id)}" aria-label="${s.isFavorite?'取消收藏':'收藏'}${esc(s.name)}" aria-pressed="${Boolean(s.isFavorite)}">${icon('heart')}</button>`;
  const heading = (title,subtitle,extra='') => `<div class="page-heading"><div><h1>${title}</h1><p>${subtitle}</p></div>${extra}</div>`;
  const empty = (title,text,action='discover',label='去发现好店',symbol='compass') => `<div class="empty-state">${icon(symbol)}<h3>${title}</h3><p>${text}</p>${action?`<button class="btn primary" data-action="nav" data-id="${action}">${label}</button>`:''}</div>`;
  const loadingHTML = () => '<div class="page-loading" role="status">正在加载这一页…</div>';
  const errorHTML = () => `<div class="page-error" role="alert"><p>${esc(pageError)}</p><button class="btn outline" data-action="retry-page">${icon('refresh')}重试加载</button></div>`;
  const pageContents = (content, emptyHTML) => loading ? loadingHTML() : pageError ? errorHTML() : page.items.length ? content : emptyHTML;
  function pagination(label) {
    if(loading || pageError)return '';
    const first=page.total? page.offset+1:0, last=Math.min(page.offset+page.items.length,page.total);
    return `<nav class="pagination" aria-label="${label}分页"><p aria-live="polite">共 ${page.total} 条 · 显示 ${first}–${last} 条</p><div><button class="btn outline" data-action="previous-page" aria-label="${label}上一页" ${page.offset===0?'disabled':''}>上一页</button><span>第 ${Math.floor(page.offset/page.limit)+1} / ${Math.max(1,Math.ceil(page.total/page.limit))} 页</span><button class="btn outline" data-action="next-page" aria-label="${label}下一页" ${!page.hasMore?'disabled':''}>下一页</button></div></nav>`;
  }
  function navigate(to) {
    clearTimeout(searchTimer); loadSerial++; modalSerial++;
    if(location.hash===`#/${to}`)readRoute();else location.hash=`/${to}`;
  }
  function readRoute() {
    ++modalSerial;
    const bits=location.hash.replace(/^#\/?/,'').split('/');
    route=bits[0] || 'discover'; currentStore=route==='store'?bits[1]:null;
    if(!['discover','group','deals','wallet','profile','merchant','store'].includes(route))route='discover';
    offset=0; page=emptyPage(route==='discover'||route==='deals'||(route==='profile'&&profileTab==='favorites')?12:10);
    detailStore=null; ownReview=null;
    loadRoute(); window.scrollTo({top:0,behavior:'instant'});
  }
  function renderChrome() {
    if($('#footer-note'))$('#footer-note').textContent=t('本地课程演示 · SQLite 持久化 · 模拟支付');
    if($('#skip-link'))$('#skip-link').textContent=t('跳到主要内容');
    $('#sidebar').setAttribute('aria-label',t('主要导航'));
    $('#mobile-nav').setAttribute('aria-label',t('移动端导航'));
    const active=route==='store'?'discover':route, unused=summary().orders.unused;
    $('#sidebar').innerHTML=t(`<button class="brand" data-action="nav" data-id="discover" aria-label="LocalDeal 首页"><span class="brand-mark"><span>L</span></span><span class="brand-word">LocalDeal<span style="color:var(--lime)">.</span></span></button><div class="sidebar-caption">YOUR CITY, YOUR PICKS</div><nav class="nav-list">${navs.map(n=>`<button title="${n.name}" class="nav-item ${active===n.id?'active':''}" data-action="nav" data-id="${n.id}" ${active===n.id?'aria-current="page"':''}>${icon(n.icon)}<span class="nav-label">${n.name}</span>${n.id==='wallet'?`<span class="nav-count">${unused}</span>`:''}</button>`).join('')}</nav><div class="sidebar-bottom"><div class="sidebar-divider"></div>${isMerchant()?`<button title="商家核销" class="nav-item ${active==='merchant'?'active':''}" data-action="nav" data-id="merchant">${icon('store')}<span class="nav-label">商家工作台</span></button>`:''}<div class="sidebar-account"><span class="avatar">${initials(state.user?.name)}</span><div><strong>${(state.user?userEsc(state.user.name):'访客')}</strong><small>${state.user?(isMerchant()?'商户账号':'顾客账号'):'浏览身边好店'}</small></div></div><p class="side-note">香港 · 本地生活探索</p></div>`);
    const name=route==='store'?storeOf(currentStore)?.name || '门店详情':[...navs,{id:'merchant',name:'商家工作台'}].find(n=>n.id===route)?.name;
    $('#header').innerHTML=t(`<div class="breadcrumb"><button class="mobile-brand only-mobile" data-action="nav" data-id="discover"><span class="brand-mark"><span>L</span></span>LocalDeal.</button><span class="desktop-crumb">LocalDeal</span><span class="desktop-crumb">/</span><strong class="desktop-crumb">${esc(name)}</strong></div><div class="top-actions"><select id="language-select" class="language-select" aria-label="Language"><option value="en" ${i18n.language==='en'?'selected':''}>English</option><option value="zh-CN" ${i18n.language==='zh-CN'?'selected':''}>&#31616;&#20307;&#20013;&#25991;</option></select><span class="location">${icon('pin')}香港</span><span class="demo-tag">LOCAL DEMO</span><button class="account-button" data-action="nav" data-id="profile"><span class="avatar">${initials(state.user?.name)}</span>${(state.user?userEsc(state.user.name):'登录')}</button></div>`);
    $('#mobile-nav').innerHTML=t(navs.map(n=>`<button class="${active===n.id?'active':''}" data-action="nav" data-id="${n.id}" ${active===n.id?'aria-current="page"':''}>${icon(n.icon)}<span>${n.name}</span></button>`).join(''));
    document.title=t(`${name} · LocalDeal`);
  }
  function storeCard(s) {
    const c=s.coupon;
    const r=s.recommendation,g=s.groupMatch;
    const insight=r?`<div class="match-insight"><strong>${r.personalized?'个性推荐':'综合推荐'} ${esc(r.score)} / 100</strong><p>${(r.reasons||[]).map(esc).join(' · ')}</p><details><summary>评分依据</summary><p>类别 ${esc(r.components.interest)} · 口碑 ${esc(r.components.reputation)} · 地区 ${esc(r.components.affinity)} · 折扣 ${esc(r.components.value_score)}</p></details></div>`:g?`<div class="match-insight"><strong>${esc(g.matchedMembers)}/${esc(g.memberCount)} 人类别匹配</strong><p>最低满意度 ${esc(g.worstScore)} · 平均 ${esc(g.meanScore)} / 100</p><p>满足全员预算 ≤ ${money(g.budgetLimit)}</p></div>`:'';
    return `<article class="store-card"><div class="store-picture"><button data-action="store" data-id="${esc(s.id)}" aria-label="查看${esc(s.name)}"><img src="${esc(s.image)}" alt="${esc(s.category)}餐饮示意照片" loading="lazy"></button>${favoriteButton(s)}<span class="photo-tag">${esc(s.category)}</span></div><div class="store-body"><div class="store-title"><button data-action="store" data-id="${esc(s.id)}">${esc(s.name)}</button>${rating(s)}</div><div class="store-sub"><span>${esc(s.district)}</span><span>人均 ${money(s.pricePerPerson)}</span><span class="review-count">${s.reviewCount} 条点评</span></div><div class="store-tags">${(s.tags||[]).slice(0,2).map(t=>`<span class="tag">${esc(t)}</span>`).join('')}</div>${validCoupon(c)?`<div class="deal-line">${icon('ticket')}<span><strong>${money(c.price)}</strong> · 原价 ${money(c.originalPrice)}</span></div>`:`<div class="deal-line muted">${icon('store')}<span>看看菜单与用户点评</span></div>`}${insight}</div></article>`;
  }
  function group() {
    return `${heading('今天，大家去哪儿吃？','先满足每位成员的预算，再按公平性与平均偏好得分推荐。')}<section class="panel group-panel"><div class="panel-heading"><h2>聚餐条件</h2><small>2–8 位成员 · 无需登录</small></div><form id="group-form"><div class="group-district"><label for="group-district">共同聚餐地区</label><select id="group-district" name="district"><option value="">所有地区</option>${(state.districts||[]).map(d=>`<option value="${esc(d.id)}" ${groupDistrict===d.id?'selected':''}>${esc(d.name)}</option>`).join('')}</select></div><div class="group-members">${groupMembers.map((m,i)=>`<fieldset class="group-member"><legend>成员 ${i+1}</legend><label for="group-budget-${i}">人均预算 (HK$)</label><input class="field" id="group-budget-${i}" name="budget-${i}" type="number" inputmode="numeric" min="1" max="10000" step="1" required value="${esc(m.budget)}"><label for="group-category-${i}">餐饮偏好</label><select id="group-category-${i}" name="category-${i}"><option value="">不限类别</option>${(state.categories||[]).map(c=>`<option value="${esc(c.id)}" ${m.category===c.id?'selected':''}>${esc(c.name)}</option>`).join('')}</select><button type="button" class="text-button" data-action="group-remove" data-id="${i}" ${groupMembers.length<=2?'disabled':''}>移除成员</button></fieldset>`).join('')}</div><div class="group-actions"><button type="button" class="btn outline" data-action="group-add" ${groupMembers.length>=8?'disabled':''}>＋ 添加成员</button><button class="btn primary" type="submit">计算聚餐推荐</button></div></form><p class="small muted">预算与共同地区为硬性限制；类别、口碑及预算余量用于评分。先最大化最低满意度，再最大化平均满意度。人均价格为门店估计值，并非实际账单。</p></section>${groupQuery?`<div class="results-heading"><h2>聚餐推荐 <span>${loading?'匹配中…':`${page.total} 家符合全员预算`}</span></h2><small>上一次提交的条件</small></div><div class="store-grid" aria-busy="${loading}">${pageContents(page.items.map(storeCard).join(''),empty('没有满足全部预算和地区的门店','尝试放宽共同地区或最低预算，再重新计算。',null))}</div>${pagination('聚餐结果')}`:empty('让每个人都参与选择','填写所有成员的预算和偏好，然后计算匹配结果。',null)}`;
  }
  function analyticsPanel(a) {
    const barMax=Math.max(1,...(a?.trend||[]).map(d=>d.gross));
    const metrics=a?[['模拟销售额',money(a.gross)],['售出券数',a.sold],['订单核销率',a.redemptionRate==null?'—':`${a.redemptionRate}%`],['今日销售额',money(a.todayGross)]]:[];
    return `<section class="panel analytics-panel"><div class="panel-heading"><div><h2>经营分析</h2><small>${esc(authorizedStores.find(s=>s.id===merchantStore)?.name||merchantStore)} · 按香港日期统计 · 模拟交易</small></div><label>统计期间 <select id="analytics-days" aria-label="经营分析期间"><option value="7" ${analyticsDays==='7'?'selected':''}>近 7 日</option><option value="30" ${analyticsDays==='30'?'selected':''}>近 30 日</option></select></label><button class="text-button" data-action="merchant-top">返回核销 ↑</button></div>${loading?loadingHTML():pageError?errorHTML():a?`<div class="analytics-stats">${metrics.map(([k,v])=>`<div class="stat-panel"><small>${k}</small><strong>${esc(v)}</strong></div>`).join('')}</div><p class="small muted">购买日期 ${esc(a.start)} 至 ${esc(a.end)} · ${a.redeemed} 已核销 / ${a.unused} 待使用 / ${a.expired} 已过期；核销率按期间内购买订单计算。</p><div class="analytics-split"><section><h3>每日销售趋势</h3><div class="trend-chart" role="img" aria-label="每日模拟销售额柱状图">${a.trend.map(d=>`<div class="trend-column" title="${esc(d.day)}：${money(d.gross)}，${d.sold} 张"><div class="trend-track"><div style="height:${Math.max(0,d.gross/barMax*100)}%"></div></div><small>${esc(d.day.slice(5))}</small></div>`).join('')}</div><p class="small muted">累计销售 ${money(a.trend.at(-1)?.cumulative||0)} · 包含无订单的日期</p></section><section><h3>优惠券销量排行</h3><div class="analytics-offers">${a.offers.length?a.offers.map(o=>`<div class="ledger-item"><div><strong>#${o.rank} ${esc(o.title)}</strong><small>销量 ${o.sold} · 销售额 ${money(o.gross)} · 核销 ${o.redeemed}</small></div><span class="${o.lowStock?'stock-alert':'small muted'}">库存 ${o.stock}${o.lowStock?' · 低库存':''}</span></div>`).join(''):'<p class="small muted">当前门店暂无优惠券。</p>'}</div></section></div>`:'<p class="small muted">暂无经营数据。</p>'}</section>`;
  }
  function analyticsDetails(a) {
    if(!a||loading||pageError)return '';
    const dates=new Map(a.ratingTrend.map(r=>[r.day,r]));
    return `<section class="panel analytics-panel"><div class="analytics-split"><section><h3>授权分店销量排行</h3>${a.branches.map(b=>`<div class="ledger-item"><div><strong>#${b.rank} ${esc(b.name)}</strong><small>${b.sold} 张 · ${money(b.gross)}</small></div>${b.id===a.storeId?'<span class="tag">当前门店</span>':''}</div>`).join('')}</section><section><h3>库存补充建议</h3><p class="small muted">按所选期间平均日销量估算未来 3 天需求；仅作演示参考。</p>${a.offers.filter(o=>o.active).map(o=>`<div class="ledger-item"><div><strong>${esc(o.title)}</strong><small>当前库存 ${o.stock} 张</small></div><span class="${o.suggestedRestock?'stock-alert':'small muted'}">${o.suggestedRestock?`建议补 ${o.suggestedRestock} 张`:'库存充足'}</span></div>`).join('')||'<p class="small muted">没有有效优惠。</p>'}</section></div><details class="analytics-data"><summary>查看每日销售、累计销售与点评明细</summary><div class="analytics-table-wrap"><table class="analytics-table"><thead><tr><th>日期</th><th>销量</th><th>模拟销售额</th><th>累计销售额</th><th>当天发表点评均分</th></tr></thead><tbody>${a.trend.map(d=>{const r=dates.get(d.day);return `<tr><td>${esc(d.day)}</td><td>${d.sold}</td><td>${money(d.gross)}</td><td>${money(d.cumulative)}</td><td>${r?`${r.average} (${r.count} 条)`:'—'}</td></tr>`;}).join('')}</tbody></table></div><p class="small muted">点评按创建日统计当前评分；已编辑或删除的点评不会保留历史版本。</p></details></section>`;
  }
  function discover() {
    const featured=state.featuredStore, c=state.featuredCoupon;
    return `${heading('今天，去哪一家？','从一杯咖啡到一顿好饭，发现你的城市日常。')}<div class="discovery-layout"><section aria-label="门店发现">${featured?`<div class="hero"><div class="hero-copy"><span class="eyebrow">THIS WEEK’S PICK</span><h2>午餐有新去处。</h2><p>${esc(featured.name)}<br>一口好味，一份小惊喜。</p><button class="btn lime" data-action="store" data-id="${esc(featured.id)}">看看这家</button></div><div class="hero-image"><img src="${esc(featured.image)}" alt="${esc(featured.category)}示意照片">${c?`<span class="hero-label"><strong>${money(c.price)}</strong> · 原价 ${money(c.originalPrice)}</span>`:''}</div></div>`:''}<div class="search-row"><label class="search-box">${icon('search')}<input id="search" type="search" value="${userEsc(filters.search)}" placeholder="搜索门店、餐品或地区" aria-label="搜索门店、餐品或地区" autocomplete="off"></label><select id="district" aria-label="筛选地区"><option value="">全部地区</option>${(state.districts||[]).map(d=>`<option value="${esc(d.id)}" ${d.id===filters.district?'selected':''}>${esc(d.name)}</option>`).join('')}</select></div><div class="category-row" aria-label="门店类别"><button class="chip ${!filters.category?'active':''}" data-action="category" data-id="" aria-pressed="${!filters.category}">${icon('grid')}全部</button>${(state.categories||[]).map(c=>`<button class="chip ${filters.category===c.id?'active':''}" data-action="category" data-id="${esc(c.id)}" aria-pressed="${filters.category===c.id}">${icon(c.name.includes('咖啡')?'coffee':'food')}${esc(c.name)}</button>`).join('')}<button class="chip ${filters.couponOnly?'active':''}" data-action="coupon-filter" aria-pressed="${filters.couponOnly}">${icon('ticket')}有优惠</button></div><div class="results-heading"><h2>值得一试 <span id="results-count">${loading?'加载中…':`${page.total} 家门店`}</span></h2><label class="sort-label">排序<select id="store-sort" aria-label="门店排序"><option value="recommended" ${filters.sort==='recommended'?'selected':''}>为你推荐</option><option value="rating" ${filters.sort==='rating'?'selected':''}>评分优先</option><option value="price" ${filters.sort==='price'?'selected':''}>人均从低到高</option></select></label></div><div id="store-grid" class="store-grid" aria-busy="${loading}">${pageContents(page.items.map(storeCard).join(''),empty('暂时没有匹配的门店','换个关键词，或清除筛选后再试。',null))}</div>${!loading&&!pageError&&!page.items.length?'<button class="text-button" data-action="clear-filters">清除筛选</button>':''}${pagination('门店')}</section><aside class="discovery-aside">${c?`<div class="ticket-feature"><span class="eyebrow">A LITTLE TREAT</span><h2>好味，也有好价。</h2><p>${esc(featured?.name || c.storeName)}</p><div class="ticket-price"><strong>${money(c.price)}</strong><s>${money(c.originalPrice)}</s></div><button class="btn primary full" data-action="buy" data-id="${esc(c.id)}" ${!validCoupon(c)?'disabled':''}>${validCoupon(c)?'查看优惠':'暂不可购买'}</button><div class="ticket-rule"><span>到店优惠券</span><span>至 ${dateText(c.expiresAt)}</span></div></div>`:''}<div class="aside-panel"><div class="aside-title"><h2>你的口袋好店</h2>${icon('heart')}</div>${sidebarFavorites.length?sidebarFavorites.map(s=>`<button class="mini-store" data-action="store" data-id="${esc(s.id)}"><img src="${esc(s.image)}" alt=""><span><strong>${esc(s.name)}</strong><small>${esc(s.district)} · ${scoreText(s)} 分</small></span></button>`).join(''):'<p class="empty-aside">点一下门店上的爱心，把下次想去的地方留在这里。</p>'}${summary().favorites>3?'<button class="text-button" data-action="nav" data-id="profile">查看全部收藏</button>':''}</div><div class="aside-panel"><div class="aside-title"><h2>我的券包</h2>${icon('wallet')}</div><div class="wallet-summary"><strong>${summary().orders.unused}</strong><span>张券待使用</span></div><button class="btn outline full" data-action="nav" data-id="wallet">打开券包</button></div><p class="aside-footnote">本地课程演示 · 数据保存于 SQLite。<br>优惠券购买使用模拟支付。</p></aside></div>`;
  }
  function reviewHTML(r, withStore=false) {
    const own=state.user?.id===r.userId;
    return `<article class="review">${withStore?`<button class="profile-review-store" data-action="store" data-id="${esc(r.storeId)}">${esc(r.storeName||storeOf(r.storeId)?.name||'门店详情')}</button>`:''}<div class="review-top"><span class="avatar">${initials(r.userName)}</span><span class="review-name">${userEsc(r.userName)}${own?' · 我':''}</span><time class="review-date" datetime="${esc(r.createdAt)}">${dateText(r.createdAt)}</time></div>${stars(r.rating)}<p>${userEsc(i18n.reviewText?i18n.reviewText(r):r.comment)}</p>${own?`<div class="review-actions"><button data-action="edit-review" data-id="${esc(r.id)}">修改点评</button><button data-action="delete-review" data-id="${esc(r.id)}">删除</button></div>`:''}</article>`;
  }
  function couponCard(c) {
    const s=storeOf(c.storeId);
    return `<article class="coupon-card"><div class="coupon-main"><button class="coupon-brand" data-action="store" data-id="${esc(c.storeId)}">${icon('store')}${esc(c.storeName||s?.name||'门店详情')} · ${esc(c.storeDistrict||s?.district||'')}</button><h3>${esc(c.title)}</h3><p class="coupon-description">${esc(c.description)}</p><div class="coupon-prices"><strong>${money(c.price)}</strong><s>${money(c.originalPrice)}</s><span class="coupon-discount">省 ${money(c.originalPrice-c.price)}</span></div></div><div class="coupon-bottom"><small>至 ${dateText(c.expiresAt)} · 剩余 ${c.stock} 张</small><button class="btn primary" data-action="buy" data-id="${esc(c.id)}" ${!validCoupon(c)?'disabled':''}>${validCoupon(c)?'查看优惠':c.stock===0?'已售罄':'暂不可购买'}</button></div></article>`;
  }
  function detail() {
    const s=detailStore;
    if(!s)return `<button class="back-button" data-action="nav" data-id="discover">${icon('back')}返回发现好店</button>${loading?loadingHTML():pageError?errorHTML():empty('这家门店没有找到','返回发现页选择其他门店。')}`;
    const c=s.coupon;
    return `<button class="back-button" data-action="nav" data-id="discover">${icon('back')}返回发现好店</button><div class="detail-cover"><img src="${esc(s.image)}" alt="${esc(s.category)}示意照片">${favoriteButton(s)}<span class="photo-tag">${esc(s.category)} · ${esc(s.district)}</span></div><div class="detail-intro"><div><h1>${esc(s.name)}</h1><p class="english-name">${esc(s.englishName)}</p><div class="detail-meta">${rating(s)}<span class="muted">${s.reviewCount} 条点评</span><span>人均 ${money(s.pricePerPerson)}</span></div></div><button class="btn outline" data-action="write-review" data-id="${esc(s.id)}" ${loading?'disabled':''}>${icon('edit')}${ownReview?'修改我的点评':'写点评'}</button></div><div class="detail-columns"><div><section class="panel"><div class="panel-heading"><h2>关于这家店</h2></div><p class="store-info">${esc(s.description)}</p><div class="info-line">${icon('pin')}<span>${esc(s.address)}</span></div><div class="info-line">${icon('clock')}<span>${esc(s.hours)}</span></div></section><section class="panel"><div class="panel-heading"><h2>招牌餐品</h2><small>价格为单品参考价</small></div><div class="menu-list">${(s.menu||[]).map(m=>`<div class="menu-item"><div><strong>${esc(m.name)}</strong><p>${esc(m.description)}</p></div><span class="menu-price">${money(m.price)}</span></div>`).join('')}</div></section><section class="panel" id="reviews"><div class="panel-heading"><h2>大家怎么说 <small>(${s.reviewCount})</small></h2><div class="review-filter"><select id="review-rating" aria-label="按星级筛选点评">${['all',5,4,3,2,1].map(n=>`<option value="${n}" ${String(n)===String(reviewRating)?'selected':''}>${n==='all'?'全部星级':`${n} 星`}</option>`).join('')}</select><select id="review-sort" aria-label="点评排序"><option value="new" ${reviewSort==='new'?'selected':''}>最新点评</option><option value="rating" ${reviewSort==='rating'?'selected':''}>评分优先</option></select></div></div><div aria-busy="${loading}">${pageContents(page.items.map(r=>reviewHTML(r)).join(''),'<p class="muted small">还没有符合条件的点评。</p>')}</div>${pagination('点评')}</section></div><aside class="detail-aside">${c?`<section class="panel store-coupon"><div class="panel-heading"><h2>${icon('ticket')} 店内优惠</h2></div>${couponCard(c)}<ul class="terms">${(c.terms||[]).map(t=>`<li>${esc(t)}</li>`).join('')}</ul></section>`:''}<section class="panel store-info-panel"><div class="panel-heading"><h2>到店之前</h2></div><p class="store-info">此券仅限购买时选择的门店使用。到店后请在券包中出示券码，由商家核销。</p><button class="btn outline full" style="margin-top:18px" data-action="nav" data-id="wallet">查看我的优惠券</button></section></aside></div>`;
  }
  function deals() {
    return `${heading('好价格，留给好日常。','给下一次到店，准备一份小优惠。')}<div class="coupon-grid" aria-busy="${loading}">${pageContents(page.items.map(couponCard).join(''),empty('暂时没有优惠券','稍后再来看看门店上新的优惠。',null))}</div>${pagination('优惠券')}`;
  }
  function orderCard(o) {
    const s=storeOf(o.storeId), status=statusOf(o);
    return `<article class="order-card"><div class="order-head"><img src="${esc(o.storeImage||s?.image||'assets/burger.jpg')}" alt=""><div><h3>${esc(o.storeName||s?.name||'门店')}</h3><p>${esc(o.storeDistrict||s?.district||'')} · 仅限本店使用</p></div><span class="status ${status}">${statusText(status)}</span></div><div class="order-body"><h2>${esc(o.title)}</h2><p class="order-price">实付 ${money(o.price)} · 购买于 ${dateText(o.purchasedAt)}</p><div class="order-code"><code>${esc(o.code)}</code>${status==='unused'?`<button data-action="copy" data-id="${esc(o.code)}">${icon('copy')}复制券码</button>`:''}</div><div class="order-footer"><span>有效期至 ${dateText(o.expiresAt)}</span><span>${status==='redeemed'?`核销于 ${dateText(o.redeemedAt)}`:status==='expired'?'已无法使用':'待商家核销'}</span></div></div></article>`;
  }
  function wallet() {
    if(!state.user)return `${heading('我的券包','下一次到店的优惠，都放在这里。')}${empty('登录后查看你的优惠券','使用邮箱与密码登录，查看你的本地课程订单。','profile','去登录','wallet')}`;
    return `${heading('我的券包','到店出示券码，让商家帮你完成核销。')}<div class="pill-tabs" aria-label="订单状态">${['all','unused','redeemed','expired'].map(t=>`<button class="pill-tab ${walletTab===t?'active':''}" data-action="wallet-tab" data-id="${t}" aria-pressed="${walletTab===t}">${t==='all'?'全部':statusText(t)} <span>(${summary().orders[t]})</span></button>`).join('')}</div><div class="wallet-grid" aria-busy="${loading}">${pageContents(page.items.map(orderCard).join(''),empty('这里还没有优惠券','去精选优惠看看，为下一顿好饭留个好价格。','deals','看看优惠','wallet'))}</div>${pagination('订单')}`;
  }
  function profile() {
    if(!state.user)return `${heading('欢迎来到 LocalDeal','登录后收藏好店、分享点评和体验优惠券。')}${empty('你的城市口袋清单','使用邮箱与密码登录，或注册你的本地课程账号。优惠券购买使用模拟支付。',null,'','user')}<div class="auth-actions" style="justify-content:center;margin:20px auto"><button class="btn primary" data-action="login">登录账号</button><button class="btn outline" data-action="register">注册新账号</button></div>`;
    const favorites=profileTab==='favorites';
    return `${heading('我的城市日常','把想去的店、尝过的好味，留在这里。',isMerchant()?'<button class="btn outline only-mobile" data-action="nav" data-id="merchant">商家核销</button>':'')}<div class="stats-row"><div class="stat-panel"><small>收藏好店</small><strong>${summary().favorites}</strong></div><div class="stat-panel"><small>我的点评</small><strong>${summary().reviews}</strong></div><div class="stat-panel"><small>待用优惠券</small><strong>${summary().orders.unused}</strong></div></div><div class="profile-layout"><aside><div class="panel profile-card"><div class="avatar">${initials(state.user.name)}</div><h2>${userEsc(state.user.name)}</h2><p>${userEsc(state.user.email)}</p><span class="profile-role">${isMerchant()?`商户账号 · ${merchantIds().length} 家授权门店`:'顾客账号'}</span><button class="btn outline" data-action="edit-profile">${icon('edit')}修改昵称</button>${isMerchant()?'<button class="btn outline" data-action="nav" data-id="merchant">商家工作台</button>':''}<button class="btn light" data-action="logout">${icon('logout')}退出账号</button></div><div class="panel"><h3>我的数据</h3><p class="small muted" style="margin:10px 0 17px">点评、收藏和订单保存于本地 SQLite 数据库。</p><button class="btn outline full" data-action="export">${icon('download')}导出我的数据</button></div></aside><section><div class="profile-menu"><button class="btn ${favorites?'primary':'outline'}" data-action="profile-tab" data-id="favorites">${icon('heart')}我的收藏</button><button class="btn ${!favorites?'primary':'outline'}" data-action="profile-tab" data-id="reviews">${icon('edit')}我的点评</button></div><div class="${favorites?'store-grid':'panel'}" aria-busy="${loading}">${pageContents(favorites?page.items.map(storeCard).join(''):page.items.map(r=>reviewHTML(r,true)).join(''),empty(favorites?'还没有收藏好店':'还没有留下点评',favorites?'浏览门店时点击爱心，收集想去的地方。':'到门店详情页，分享你的体验。'))}</div>${pagination(favorites?'收藏':'我的点评')}</section></div>`;
  }
  function merchant() {
    if(!state.user)return `${heading('商家工作台','登录商户账号，查看门店订单与核销优惠券。')}${empty('请先登录商户账号','登录窗口列出了课程演示商户账号。',null,'','store')}<button class="btn primary" style="display:flex;margin:20px auto" data-action="login">登录商户账号</button>`;
    if(!isMerchant())return `${heading('商家工作台','门店订单与核销仅对授权商户开放。')}${empty('此账号没有商户权限','顾客账号可以在券包查看自己的订单。若要体验商户操作，请退出后登录示例商户账号。','profile','返回个人中心','shield')}`;
        return `${heading('商家工作台','核对授权门店，用券码完成到店核销。','<button class="btn primary" data-action="analytics-jump">经营分析 ↓</button>')}<div class="merchant-layout"><section class="panel"><div class="panel-heading"><h2>优惠券核销</h2>${icon('shield')}</div><label class="merchant-label" for="merchant-store">当前授权门店</label><select id="merchant-store">${merchantIds().map(id=>`<option value="${esc(id)}" ${id===merchantStore?'selected':''}>${esc(authorizedStores.find(s=>s.id===id)?.name||storeOf(id)?.name||id)}</option>`).join('')}</select><form id="redeem-form" class="merchant-form"><p>请核对门店后，输入顾客券包中的券码。</p><label class="merchant-label" for="redeem-code">优惠券码</label><input class="field" id="redeem-code" name="code" placeholder="例如 LD-…" required autocomplete="off" maxlength="64"><div class="form-error" id="redeem-error" role="alert"></div><button class="btn primary full" type="submit" ${!merchantStore||loading?'disabled':''}>${icon('check')}确认核销</button></form>${redemptionResult?`<div class="redemption-result"><h3>${icon('check')}核销成功</h3><p>${esc(redemptionResult.title)}<br>${esc(redemptionResult.code)}<br>${esc(storeOf(redemptionResult.storeId)?.name||'')}</p></div>`:''}<div class="merchant-notice">你只能查看和核销当前账号有员工权限的门店。核销结果会保存到本地数据库。</div></section><section class="panel"><div class="panel-heading"><h2>本店订单</h2><small>${loading?'加载中…':`${page.total} 条`}</small></div><label class="merchant-label" for="merchant-status">订单状态</label><select id="merchant-status" aria-label="筛选商户订单状态">${['all','unused','redeemed','expired'].map(s=>`<option value="${s}" ${s===merchantStatus?'selected':''}>${s==='all'?'全部状态':statusText(s)}</option>`).join('')}</select><div aria-busy="${loading}">${pageContents(page.items.map(o=>`<div class="ledger-item"><div><strong>${esc(o.title)}</strong><small>${esc(o.code)} · ${dateText(o.purchasedAt)}${o.userName?` · ${userEsc(o.userName)}`:''}</small></div><span class="status ${statusOf(o)}">${statusText(statusOf(o))}</span></div>`).join(''),'<p class="small muted merchant-empty">当前门店还没有符合条件的订单。</p>')}</div>${pagination('商户订单')}<div class="merchant-notice">过期券、其他门店的券，以及已经核销的券，都不能再次使用。</div></section></div>`;
  }
  function render() {
    if(!state)return;
    const focus=document.activeElement, focusID=focus?.id;
    const position=focusID==='search'?{start:focus.selectionStart,end:focus.selectionEnd}:null;
    const redeemValue=$('#redeem-code')?.value;
    renderChrome(); $('#main').innerHTML=t(({discover,group,deals,wallet,profile,merchant:()=>merchant()+(isMerchant()?analyticsPanel(merchantAnalytics)+analyticsDetails(merchantAnalytics):''),store:detail}[route]||discover)());
    if(pending&&$('#merchant-store'))$('#merchant-store').disabled=true;
    if(route==='merchant'&&redeemValue!==undefined&&$('#redeem-code'))$('#redeem-code').value=redeemValue;
    if(focusID) {
      const target=document.getElementById(focusID);
      if(target) {
        target.focus({preventScroll:true});
        if(position&&target.setSelectionRange)try{target.setSelectionRange(position.start,position.end);}catch{}
      }
    }
  }
  // A response may update the screen only if its route/filter generation is current.
  async function loadRoute() {
    if(!state)return;
    const serial=++loadSerial, viewRoute=route, storeID=currentStore;
    const limit=['discover','group','deals'].includes(viewRoute)||(viewRoute==='profile'&&profileTab==='favorites')?12:10;
    loading=true; pageError=''; page=emptyPage(limit); page.offset=offset; render();
    try {
      let result=emptyPage(limit), fetchedStore=null, side=[], names=[], mine=null, analytics=null;
      const query={limit,offset};
      if(viewRoute==='discover') {
        [result, side]=await Promise.all([
          API.getStores({...query,q:i18n.searchTerm?i18n.searchTerm(filters.search):filters.search.trim(),district:filters.district,category:filters.category,sort:filters.sort,couponOnly:filters.couponOnly}),
          state.user&&summary().favorites>0?API.getMyFavorites({limit:3,offset:0}).then(p=>p.items):Promise.resolve([])
        ]);
      } else if(viewRoute==='group'&&groupQuery) result=await API.getGroupMatch({...query,...groupQuery});
      else if(viewRoute==='deals') result=await API.getCoupons(query);
      else if(viewRoute==='store') {
        const values=await Promise.all([API.getStore(storeID),API.getStoreReviews(storeID,{...query,rating:reviewRating,sort:reviewSort})]);
        fetchedStore=values[0]; result=values[1]; mine=result.ownReview || null;
      } else if(viewRoute==='wallet'&&state.user)result=await API.getOrders({...query,status:walletTab});
      else if(viewRoute==='profile'&&state.user)result=profileTab==='favorites'?await API.getMyFavorites(query):await API.getMyReviews(query);
      else if(viewRoute==='merchant'&&isMerchant()) {
        if(!merchantIds().includes(merchantStore))merchantStore=merchantIds()[0] || '';
        const nameIDs=[...new Set([merchantStore,...merchantIds().slice(0,10)])].filter(Boolean);
        [result,names,analytics]=await Promise.all([
          API.getMerchantOrders({...query,storeId:merchantStore,status:merchantStatus}),
          Promise.all(nameIDs.map(id=>storeOf(id)?Promise.resolve(storeOf(id)):API.getStore(id))),
          API.getMerchantAnalytics({storeId:merchantStore,days:analyticsDays})
        ]);
      }
      if(serial!==loadSerial)return;
      // Removing the last item on the last page should reveal the previous page.
      if(offset>0 && result.items.length===0 && offset>=result.total) {
        offset=result.total?Math.floor((result.total-1)/limit)*limit:0; await loadRoute(); return;
      }
      page=result; offset=result.offset; sidebarFavorites=side;
      if(viewRoute==='store') {detailStore=fetchedStore;ownReview=mine;rememberStore(fetchedStore);}
      if(viewRoute==='merchant'){authorizedStores=names;merchantAnalytics=analytics;}
      names.forEach(rememberStore); side.forEach(rememberStore);
      if(['discover','group'].includes(viewRoute)||(viewRoute==='profile'&&profileTab==='favorites'))result.items.forEach(rememberStore);
      if(viewRoute==='deals')result.items.forEach(c=>remember(coupons,c));
      if(viewRoute==='store'||(viewRoute==='profile'&&profileTab==='reviews'))result.items.forEach(r=>remember(reviews,r,32));
      if(mine)remember(reviews,mine,32);
    } catch(problem) {
      if(serial!==loadSerial)return;
      if(problem.status===401){await recoverSession();return;}
      pageError=problem.message || '这一页暂时无法加载，请重试。';
    } finally {
      if(serial===loadSerial){loading=false;render();}
    }
  }
  async function refresh() {
    clearTimeout(searchTimer); ++loadSerial;
    const serial=++bootstrapSerial, next=await API.getState();
    if(serial!==bootstrapSerial)return;
    if(next.user?.id!==state?.user?.id){++modalSerial;merchantStore='';redemptionResult=null;offset=0;}
    state=next; stores.clear();coupons.clear();reviews.clear();authorizedStores=[];sidebarFavorites=[];merchantAnalytics=null;
    detailStore=null;ownReview=null;
    rememberStore(next.featuredStore); if(next.featuredCoupon)remember(coupons,next.featuredCoupon);
    await loadRoute();
  }
  async function recoverSession() {
    ++loadSerial; ++modalSerial;
    const serial=++bootstrapSerial;
    state={...state,user:null,csrfToken:null,summary:{favorites:0,reviews:0,orders:{all:0,unused:0,redeemed:0,expired:0}}};
    if(state.featuredStore)state.featuredStore={...state.featuredStore,isFavorite:false};
    stores.clear();coupons.clear();reviews.clear();authorizedStores=[];sidebarFavorites=[];merchantAnalytics=null;
    merchantStore='';redemptionResult=null;ownReview=null;detailStore=null;offset=0;
    page=emptyPage(12);pageError='';loading=false;render();
    try {
      const next=await API.getState();
      if(serial!==bootstrapSerial)return;
      state=next;rememberStore(next.featuredStore);
      if(next.featuredCoupon)remember(coupons,next.featuredCoupon);
      await loadRoute();
    } catch {
      // Guest navigation remains available when the service is temporarily down.
    }
    if(serial===bootstrapSerial&&!state.user){toast('登录已过期，请重新登录。',true);loginDialog();}
  }
  function toast(text,error=false) {
    const el=document.createElement('div');el.className=`toast ${error?'error':''}`;el.innerHTML=t(`${icon(error?'close':'check')}<span>${esc(text)}</span>`);$('#toasts').replaceChildren(el);setTimeout(()=>el.remove(),4000);
  }
  function showModal(title,body) {
    ++modalSerial;
    const m=$('#modal');m.innerHTML=t(`<div class="modal-head"><h2 id="modal-title">${title}</h2><button class="icon-button" data-action="close" aria-label="关闭">${icon('close')}</button></div><div class="modal-body">${body}</div>`);if(!m.open)m.showModal();
  }
  function closeModal(){if(!pending){++modalSerial;$('#modal').close();}}
  const demoAccounts = () => '<div class="auth-note"><strong>课程演示账号</strong><p>顾客：<code>alex@example.com</code><br>Harbor Bites 商户：<code>harbor.owner@example.com</code><br>Little Dumpling 商户：<code>dumpling.owner@example.com</code><br>Daily Grind 商户：<code>coffee.owner@example.com</code></p><p>以上虚构账号的示例密码：<code>LocalDealDemo!2026</code></p></div>';
  function loginDialog() {
    showModal('登录 LocalDeal',`<p>使用邮箱与密码进入你的本地课程账号。</p><form id="login-form"><label for="login-email">邮箱</label><input id="login-email" class="field" name="email" type="email" value="${userEsc(state?.user?.email||'')}" placeholder="alex@example.com" required maxlength="254" autocomplete="username"><label for="login-password">密码</label><input id="login-password" class="field" name="password" type="password" placeholder="输入密码" required maxlength="128" autocomplete="current-password"><div class="form-error" role="alert"></div><button class="btn primary full" type="submit">登录账号</button><p class="modal-note">还没有账号？<button type="button" class="text-button" data-action="register">注册新账号</button></p></form>${demoAccounts()}`);
  }
  function registerDialog() {
    showModal('注册 LocalDeal 账号','<p>注册顾客账号，建立自己的收藏、点评与券包。</p><form id="register-form"><label for="register-name">昵称</label><input id="register-name" class="field" name="name" placeholder="你的昵称" required maxlength="60" autocomplete="nickname"><label for="register-email">邮箱</label><input id="register-email" class="field" name="email" type="email" placeholder="你的邮箱" required maxlength="254" autocomplete="username"><label for="register-password">密码</label><input id="register-password" class="field" name="password" type="password" placeholder="至少 12 个字符" minlength="12" maxlength="128" required autocomplete="new-password"><label for="register-confirm">确认密码</label><input id="register-confirm" class="field" name="confirmPassword" type="password" minlength="12" maxlength="128" required autocomplete="new-password"><div class="form-error" role="alert"></div><button class="btn primary full" type="submit">创建账号</button><p class="modal-note">已有账号？<button type="button" class="text-button" data-action="login">返回登录</button></p></form>');
  }
  function requireLogin(){if(state.user)return true;loginDialog();return false;}
  function profileDialog() {
    if(!requireLogin())return;
    showModal('修改昵称',`<form id="profile-form"><label for="profile-name">昵称</label><input id="profile-name" class="field" name="name" value="${userEsc(state.user.name)}" required maxlength="60" autocomplete="nickname"><p class="modal-note">已发表的点评也会显示更新后的昵称。</p><div class="form-error" role="alert"></div><div class="modal-actions"><button type="button" class="btn outline" data-action="close">取消</button><button type="submit" class="btn primary">保存昵称</button></div></form>`);
  }
  async function reviewDialog(storeId,id) {
    if(!requireLogin())return;
    const serial=++modalSerial,userID=state.user.id,viewRoute=route,viewStore=currentStore;
    let r=id?reviews.get(id):ownReview;
    // Own review is independent of the visible page and star filter.
    if(!id&&(!r||r.storeId!==storeId))r=(await API.getStoreReviews(storeId,{limit:1,offset:0,rating:'all',sort:'new'})).ownReview;
    const s=storeOf(storeId)||await API.getStore(storeId);
    if(serial!==modalSerial||state.user?.id!==userID||route!==viewRoute||currentStore!==viewStore)return;
    rememberStore(s);
    modalRating=r?.rating||5;
    showModal(r?'修改你的点评':'分享你的体验',`<p>${esc(s.name)}</p><form id="review-form" data-store="${esc(storeId)}" data-review="${esc(r?.id||'')}"><label>你的评分</label><div class="stars-input" role="group" aria-label="选择评分">${[1,2,3,4,5].map(n=>`<button type="button" class="${n<=modalRating?'selected':''}" data-action="rating" data-id="${n}" aria-label="${n} 星" aria-pressed="${n===modalRating}">${icon('star')}</button>`).join('')}</div><label for="review-comment">点评内容</label><textarea id="review-comment" class="field" name="comment" minlength="5" maxlength="500" required placeholder="餐品、环境或服务，有哪些值得分享？">${userEsc(r?.comment||'')}</textarea><p class="modal-note">5–500 个字符。点评将以当前昵称显示。</p><div class="form-error" role="alert"></div><div class="modal-actions"><button type="button" class="btn outline" data-action="close">取消</button><button type="submit" class="btn primary">${r?'保存修改':'发布点评'}</button></div></form>`);
  }
  async function buyDialog(id) {
    if(!requireLogin())return;
    const serial=++modalSerial,userID=state.user.id,viewRoute=route,viewStore=currentStore;
    const c=await API.getCoupon(id), s=storeOf(c.storeId)||await API.getStore(c.storeId);
    if(serial!==modalSerial||state.user?.id!==userID||route!==viewRoute||currentStore!==viewStore)return;
    remember(coupons,c);rememberStore(s);
    const key=window.crypto?.randomUUID?.() || `purchase-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
    showModal('确认购买优惠券',`<div class="checkout-summary"><h3>${esc(c.title)}</h3><p>${esc(s.name)} · 仅限本店使用</p><div class="total-row"><span>模拟支付金额</span><strong>${money(c.price)}</strong></div></div><ul class="terms">${(c.terms||[]).map(t=>`<li>${esc(t)}</li>`).join('')}<li>有效期至 ${esc(c.expiresAt.slice(0,10))}，剩余 ${c.stock} 张。</li></ul><p class="modal-note">课程演示使用模拟支付，不会扣取真实款项。订单会保存到本地数据库，确认后可在“我的券包”查看券码。</p><form id="purchase-form" data-coupon="${esc(c.id)}" data-key="${esc(key)}"><div class="form-error" role="alert"></div><div class="modal-actions"><button type="button" class="btn outline" data-action="close">再想想</button><button type="submit" class="btn primary" ${!validCoupon(c)?'disabled':''}>确认模拟购买</button></div></form>`);
  }
  async function run(task,success) {
    try{await task();await refresh();if(success)toast(success);}
    catch(problem){if(problem.status===401)await recoverSession();else toast(problem.message||'操作未完成，请再试一次。',true);}
  }
  const resetPage = () => {offset=0;loadRoute();};
  document.addEventListener('click',async event=>{
    const el=event.target.closest('[data-action]');if(!el||el.disabled)return;
    const a=el.dataset.action,id=el.dataset.id;
    if(pending&&['close','login','register','edit-profile','buy','write-review','edit-review','delete-review'].includes(a))return;
    try {
      if(a==='retry')await start();
      else if(a==='retry-page')await loadRoute();
      else if(a==='nav')navigate(id);
      else if(a==='analytics-jump')$('.analytics-panel')?.scrollIntoView({behavior:'smooth',block:'start'});
      else if(a==='merchant-top')window.scrollTo({top:0,behavior:'smooth'});
      else if(a==='group-add'&&groupMembers.length<8){groupMembers.push({budget:'120',category:''});render();}
      else if(a==='group-remove'&&groupMembers.length>2){groupMembers.splice(Number(id),1);render();}
      else if(a==='store'){reviewSort='new';reviewRating='all';navigate(`store/${id}`);}
      else if(a==='favorite') {
        if(requireLogin())await run(()=>API.toggleFavorite(id),storeOf(id)?.isFavorite?'已取消收藏':'已加入口袋好店');
      } else if(a==='category'){clearTimeout(searchTimer);filters.category=id;resetPage();}
      else if(a==='coupon-filter'){clearTimeout(searchTimer);filters.couponOnly=!filters.couponOnly;resetPage();}
      else if(a==='clear-filters'){clearTimeout(searchTimer);filters={search:'',category:'',district:'',sort:'recommended',couponOnly:false};resetPage();}
      else if(a==='wallet-tab'){walletTab=id;resetPage();}
      else if(a==='profile-tab'){profileTab=id;resetPage();}
      else if(a==='previous-page'&&!loading){offset=Math.max(0,page.offset-page.limit);await loadRoute();}
      else if(a==='next-page'&&!loading&&page.hasMore){offset=page.offset+page.limit;await loadRoute();}
      else if(a==='write-review')await reviewDialog(id);
      else if(a==='edit-review'){const r=reviews.get(id);if(r)await reviewDialog(r.storeId,r.id);}
      else if(a==='delete-review')showModal('删除这条点评？',`<p>删除后，这条点评将从门店页面移除，平均评分也会更新。</p><form id="delete-form" data-review="${esc(id)}"><div class="form-error" role="alert"></div><div class="modal-actions"><button type="button" class="btn outline" data-action="close">保留点评</button><button type="submit" class="btn danger">确认删除</button></div></form>`);
      else if(a==='rating'){modalRating=Number(id);$('.stars-input').querySelectorAll('button').forEach(b=>{b.classList.toggle('selected',Number(b.dataset.id)<=modalRating);b.setAttribute('aria-pressed',Number(b.dataset.id)===modalRating);});}
      else if(a==='buy')await buyDialog(id);
      else if(a==='close')closeModal();
      else if(a==='login')loginDialog();
      else if(a==='register')registerDialog();
      else if(a==='edit-profile')profileDialog();
      else if(a==='logout')await run(()=>API.logout(),'已退出账号');
      else if(a==='copy') {
        try{if(!navigator.clipboard)throw Error();await navigator.clipboard.writeText(id);toast('券码已复制');}
        catch{showModal('你的优惠券码',`<p>选中下面的券码，按 ⌘C 或 Ctrl+C 复制。</p><input class="field" value="${esc(id)}" readonly aria-label="优惠券码"><p class="modal-note">到店后向对应门店员工出示此券码。</p>`);$('.field',$('#modal')).select();}
      } else if(a==='export') {
        const data=await API.exportData(), blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json'});
        const url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download='localdeal-my-data.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);toast('我的数据已导出');
      }
    } catch(problem){if(problem.status===401)await recoverSession();else toast(problem.message||'操作未完成，请重试。',true);}
  });
  document.addEventListener('input',event=>{
    const member=event.target.id?.match(/^group-budget-(\d+)$/);
    if(member&&groupMembers[Number(member[1])])groupMembers[Number(member[1])].budget=event.target.value;
    if(event.target.id==='search') {
      filters.search=event.target.value;offset=0;
      // Invalidate already-running searches before the next debounced request.
      clearTimeout(searchTimer);++loadSerial;
      searchTimer=setTimeout(()=>{if(route==='discover')loadRoute();},300);
    }
  });
  document.addEventListener('change',event=>{
    const id=event.target.id,v=event.target.value;
    if(id==='language-select'){i18n.set(v);render();return;}
    if(id==='district'){clearTimeout(searchTimer);filters.district=v;resetPage();}
    else if(id==='store-sort'){clearTimeout(searchTimer);filters.sort=v;resetPage();}
    else if(id==='review-sort'){reviewSort=v;resetPage();}
    else if(id==='review-rating'){reviewRating=v;resetPage();}
    else if(id==='merchant-store'){if(pending){event.target.value=merchantStore;return;}merchantStore=v;redemptionResult=null;resetPage();}
    else if(id==='merchant-status'){merchantStatus=v;resetPage();}
    else if(id==='analytics-days'){analyticsDays=v;resetPage();}
    else if(id==='group-district')groupDistrict=v;
    else if(id?.startsWith('group-category-')){const member=groupMembers[Number(id.split('-').at(-1))];if(member)member.category=v;}
  });
  document.addEventListener('submit',async event=>{
    const f=event.target;
    if(f.id==='group-form'){
      event.preventDefault();
      const values=new FormData(f);
      groupDistrict=values.get('district')||'';
      groupMembers=groupMembers.map((m,i)=>({budget:String(values.get(`budget-${i}`)||''),category:values.get(`category-${i}`)||''}));
      if(groupMembers.some(m=>!/^\d+$/.test(m.budget)||Number(m.budget)<1||Number(m.budget)>10000)){toast('每位成员需填写 1–10000 港元的整数预算。',true);return;}
      groupQuery={district:groupDistrict,members:groupMembers.map(m=>({budget:Number(m.budget),category:m.category}))};
      offset=0;await loadRoute();return;
    }
    if(!['login-form','register-form','profile-form','review-form','purchase-form','redeem-form','delete-form'].includes(f.id))return;
    event.preventDefault();if(pending)return;pending=true;
    const err=$('.form-error',f);if(err)err.textContent='';
    const submit=$('[type="submit"]',f);submit.disabled=true;
    const selectedStore=$('#merchant-store'), redemptionStore=merchantStore, redemptionUser=state.user?.id;
    if(f.id==='redeem-form'&&selectedStore)selectedStore.disabled=true;
    const values=new FormData(f);
    try {
      let message;
      if(f.id==='login-form'){await API.login({email:values.get('email'),password:values.get('password')});message='登录成功';}
      if(f.id==='register-form'){if(values.get('password')!==values.get('confirmPassword'))throw new Error('两次输入的密码不一致，请检查。');await API.register({name:values.get('name'),email:values.get('email'),password:values.get('password')});message='账号已创建';}
      if(f.id==='profile-form'){await API.updateProfile({name:values.get('name')});message='昵称已更新';}
      if(f.id==='review-form'){await API.saveReview({storeId:f.dataset.store,rating:modalRating,comment:values.get('comment'),...(f.dataset.review?{id:f.dataset.review}:{})});message=f.dataset.review?'点评已更新':'点评已发布';}
      if(f.id==='purchase-form'){await API.purchase(f.dataset.coupon,f.dataset.key);walletTab='unused';offset=0;message='购买成功，优惠券已放入券包';}
      if(f.id==='redeem-form'){
        const result=await API.redeem({code:values.get('code'),storeId:redemptionStore});
        if(merchantStore===redemptionStore&&state.user?.id===redemptionUser)redemptionResult=result;
        message='优惠券已核销';
      }
      if(f.id==='delete-form'){await API.deleteReview(f.dataset.review);message='点评已删除';}
      // Change the route before refresh to fetch only the destination page.
      if(f.id==='purchase-form'){route='wallet';currentStore=null;}
      if(f.id==='login-form'||f.id==='register-form'){route='profile';currentStore=null;}
      await refresh();
      if(f.id!=='redeem-form')$('#modal').close();
      if(f.id==='purchase-form'||f.id==='login-form'||f.id==='register-form') {
        const hash=`#/${route}`;if(location.hash!==hash){history.replaceState(null,'',hash);render();}
      }
      toast(message);
    } catch(problem) {
      if(problem.status===401&&f.id!=='login-form'&&f.id!=='register-form')await recoverSession();
      else if(err)err.textContent=t((problem.message||'操作未完成，请重试。')+(f.id==='purchase-form'&&problem.code==='NETWORK_ERROR'?' 再次确认会继续本次购买。':''));
      else toast(problem.message,true);
    } finally{pending=false;submit.disabled=false;if($('#merchant-store'))$('#merchant-store').disabled=false;}
  });
  $('#modal').addEventListener('click',e=>{if(e.target===$('#modal')){const r=e.target.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)closeModal();}});
  $('#modal').addEventListener('cancel',e=>{if(pending)e.preventDefault();else ++modalSerial;});
  window.addEventListener('hashchange',readRoute);
  async function start() {
    $('#main').innerHTML=t('<div class="loading" role="status">正在连接本地服务…</div>');
    try {
      if(!API)throw new Error('页面接口未能加载，请通过 LocalDeal 启动器打开应用。');
      const next=await API.getState();state=next;
      rememberStore(next.featuredStore);if(next.featuredCoupon)remember(coupons,next.featuredCoupon);
      readRoute();
    } catch(problem) {
      $('#main').innerHTML=t(`${empty('暂时无法连接 LocalDeal',esc(problem.message||'请检查本地服务是否已启动。'),null)}<button class="btn primary error-retry" style="display:flex;margin:20px auto" data-action="retry">${icon('refresh')}重新连接</button>`);
    }
  }
  start();
})();
