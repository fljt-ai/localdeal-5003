// State/event regression checks; real DOM layout is validated separately in a browser.
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../src/app.js'),'utf8');
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};};
const flush=async()=>{for(let i=0;i<25;i++)await Promise.resolve();};
const store=(id='s1',name='Test store')=>({id,name,englishName:name,category:'西式餐厅',district:'中环',image:'assets/burger.jpg',pricePerPerson:50,tags:[],menu:[],averageRating:4.5,reviewCount:999,isFavorite:false,coupon:null,address:'Test address',hours:'10:00–20:00',description:'Test description'});
const paged=(items=[],total=items.length,limit=12,offset=0)=>({items,total,limit,offset,hasMore:offset+items.length<total});
const user={id:'u1',name:'Alex',email:'alex@example.com',merchantStoreIds:[]};
const bootstrap=(person=user)=>({user:person,csrfToken:person?'csrf':null,summary:{favorites:2,reviews:50,orders:{all:30,unused:20,redeemed:5,expired:5}},categories:[],districts:[],featuredStore:store(),featuredCoupon:null});
function harness(initialHash='#/discover',person=user,overrides={},language=null) {
  const nodes=new Map(),events={},windowEvents={},timers=new Map();
  let timerID=0,hash=initialHash;
  class Element {
    constructor(id=''){this.id=id;this.value='';this.open=false;this.disabled=false;this.dataset={};this.ids=[];this.selectionStart=0;this.selectionEnd=0;this.classList={toggle(){}};}
    set innerHTML(html) {
      this.html=html;
      this.ids.forEach(id=>nodes.delete(id));this.ids=[];
      for(const match of html.matchAll(/<[^>]*\bid="([^"]+)"[^>]*>/g)) {
        const child=new Element(match[1]);
        child.value=match[0].match(/\bvalue="([^"]*)"/)?.[1] || '';
        nodes.set(child.id,child);this.ids.push(child.id);
      }
    }
    get innerHTML(){return this.html||'';}
    querySelector(selector){return this.fields?.[selector]||document.querySelector(selector);}
    querySelectorAll(){return [];}
    showModal(){this.open=true;}
    close(){this.open=false;}
    focus(){document.activeElement=this;}
    setSelectionRange(start,end){this.selectionStart=start;this.selectionEnd=end;}
    addEventListener(name,fn){events[`${this.id}:${name}`]=fn;}
    replaceChildren(){ }
    remove(){ }
    setAttribute(){ }
  }
  ['main','sidebar','header','mobile-nav','modal','toasts'].forEach(id=>nodes.set(id,new Element(id)));
  const document={
    documentElement:{lang:''},
    activeElement:null,title:'',
    querySelector:selector=>nodes.get(selector.replace(/^#/,'')) || null,
    getElementById:id=>nodes.get(id) || null,
    addEventListener:(name,fn)=>{events[name]=fn;},
    createElement:()=>new Element()
  };
  const calls=[];
  let currentBootstrap=bootstrap(person);
  const api={
    getState:async()=>currentBootstrap,
    getStores:async q=>{calls.push(['stores',q]);return paged([store()]);},
    getGroupMatch:async q=>{calls.push(['group',q]);return paged([{...store(),groupMatch:{memberCount:2,matchedMembers:2,worstScore:91,meanScore:93,budgetLimit:100}}]);},
    getStore:async id=>store(id,id==='s2'?'Second store':'Test store'),
    getCoupons:async()=>paged([]),
    getCoupon:async()=>({id:'c1',storeId:'s1',title:'Test coupon',terms:[],expiresAt:'2026-12-01',stock:10,price:50,originalPrice:60,isPurchasable:true}),
    getStoreReviews:async()=>({...paged([],0,10),ownReview:null}),
    getMyFavorites:async()=>paged([store()]),
    getMyReviews:async()=>paged([],0,10),
    getOrders:async()=>paged([],0,10),
    getMerchantOrders:async()=>paged([],0,10),
    getMerchantAnalytics:async q=>({storeId:q.storeId,days:Number(q.days),start:'2026-11-21',end:'2026-11-27',sold:1,gross:50,redeemed:0,unused:1,expired:0,redemptionRate:0,todayGross:50,trend:[{day:'2026-11-27',gross:50,sold:1,cumulative:50}],offers:[],branches:[],ratingTrend:[]}),
    getOrderStatus:order=>order.status,
    logout:async()=>{currentBootstrap=bootstrap(null);},
    ...overrides
  };
  const location={};
  Object.defineProperty(location,'hash',{get:()=>hash,set:value=>{hash=value;queueMicrotask(()=>windowEvents.hashchange?.());}});
  const sandbox={
    document,location,navigator:{},history:{replaceState:(_a,_b,value)=>{hash=value;}},
    window:{LocalDealAPI:api,scrollTo(){},addEventListener:(name,fn)=>{windowEvents[name]=fn;},crypto:{randomUUID:()=> 'intent-key'}},
    FormData:class{constructor(form){this.values=form.values;}get(name){return this.values[name];}},
    setTimeout:(fn,delay)=>{const id=++timerID;timers.set(id,{fn,delay});return id;},
    clearTimeout:id=>timers.delete(id)
  };
  const preferences={};
  if(language!==null){
    if(language)preferences['localdeal-language']=language;
    sandbox.localStorage={getItem:key=>preferences[key]||null,setItem:(key,value)=>{preferences[key]=value;}};
    vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../src/i18n.js'),'utf8'),sandbox);
  }
  vm.runInNewContext(source,sandbox);
  return {
    api,document,calls,nodes,preferences,
    get main(){return nodes.get('main').innerHTML;},
    get modal(){return nodes.get('modal');},
    setBootstrap:value=>{currentBootstrap=value;},
    click:async(action,id='')=>events.click({target:{closest:()=>({dataset:{action,id},disabled:false})}}),
    input:value=>{const target=nodes.get('search');target.value=value;target.focus();events.input({target});},
    runSearchTimer:()=>{for(const [id,t]of timers)if(t.delay===300){timers.delete(id);t.fn();}},
    change:(id,value)=>{const target=nodes.get(id);target.value=value;events.change({target});},
    submit:async(formID,values)=>{
      const form=new Element(formID);form.values=values;
      form.fields={'.form-error':new Element(),'[type="submit"]':new Element()};
      return events.submit({target:form,preventDefault(){}});
    }
  };
}
(async()=>{
  const bilingual=harness('#/discover',null,{},'');await flush();
  assert.equal(bilingual.document.documentElement.lang,'en');
  assert.match(bilingual.main,/Where shall we eat today\?/);
  assert.match(bilingual.nodes.get('header').innerHTML,/language-select/);
  bilingual.change('language-select','zh-CN');await flush();
  assert.equal(bilingual.preferences['localdeal-language'],'zh-CN');
  assert.match(bilingual.main,/今天，去哪一家？/);
  bilingual.change('language-select','en');await flush();
  assert.equal(bilingual.preferences['localdeal-language'],'en');
  assert.match(bilingual.main,/Where shall we eat today\?/);
  bilingual.input('coffee');bilingual.runSearchTimer();await flush();
  assert.equal(bilingual.calls.at(-1)[1].q,'咖啡');
  const originalReview={id:'r-original',storeId:'s1',userId:'other',userName:'中文用户',rating:5,comment:'我喜欢咖啡',createdAt:'2026-11-27'};
  const bilingualReview=harness('#/store/s1',null,{getStoreReviews:async()=>({...paged([originalReview],1,10),ownReview:null})},'en');await flush();
  assert.match(bilingualReview.main,/&#25105;&#21916;&#27426;&#21654;&#21857;/);
  assert.doesNotMatch(bilingualReview.main,/Me喜欢Coffee/);
  const seedReview={...originalReview,id:'r-s1-1',comment:'汉堡现做又多汁，松露薯条很香，和朋友吃得很满足。'};
  const translatedSeed=harness('#/store/s1',null,{getStoreReviews:async()=>({...paged([seedReview],1,10),ownReview:null})},'en');await flush();
  assert.match(translatedSeed.main,/Fresh, juicy burgers/);
  const editedSeed=harness('#/store/s1',null,{getStoreReviews:async()=>({...paged([{...seedReview,comment:'我喜欢咖啡'}],1,10),ownReview:null})},'en');await flush();
  assert.match(editedSeed.main,/&#25105;&#21916;&#27426;&#21654;&#21857;/);
  const old=deferred(),latest=deferred();
  const discovery=harness('#/discover',user,{getStores:async query=>query.q==='old'?old.promise:query.q==='new'?latest.promise:paged([store()])});
  await flush();
  assert.match(discovery.main,/999 条点评/); // Whole-store count, rather than loaded reviews.
  discovery.input('old');discovery.runSearchTimer();await flush();
  discovery.input('new');discovery.runSearchTimer();await flush();
  latest.resolve(paged([store('current','Current result')]));await flush();
  old.resolve(paged([store('stale','Stale result')]));await flush();
  assert.match(discovery.main,/Current result/);assert.doesNotMatch(discovery.main,/Stale result/);
  assert.equal(discovery.document.activeElement.id,'search');
  assert.equal(discovery.nodes.get('search').value,'new');

  const group=harness('#/group',null);await flush();
  assert.match(group.main,/聚餐条件/);
  await group.submit('group-form',{'budget-0':'100','category-0':'cat-coffee','budget-1':'120','category-1':'','district':'central'});await flush();
  const match=group.calls.find(c=>c[0]==='group');
  assert.equal(match[1].members[0].budget,100);assert.equal(match[1].district,'central');
  assert.match(group.main,/2\/2 人类别匹配/);assert.match(group.main,/最低满意度 91/);

  const own={id:'own-hidden',storeId:'s1',userId:'u1',userName:'Alex',rating:5,comment:'My review outside this page',createdAt:'2026-10-03'};
  const detail=harness('#/store/s1',user,{getStoreReviews:async()=>({...paged([],40,10),ownReview:own})});
  await flush();
  assert.match(detail.main,/修改我的点评/);
  await detail.click('write-review','s1');
  assert.match(detail.modal.innerHTML,/data-review="own-hidden"/);
  assert.match(detail.modal.innerHTML,/My review outside this page/);
  await detail.click('close');
  const couponWait=deferred();detail.api.getCoupon=()=>couponWait.promise;
  const openPurchase=detail.click('buy','c1');await flush();
  await detail.click('nav','profile');await flush();
  couponWait.resolve({id:'c1',storeId:'s1',title:'Late coupon',terms:[],expiresAt:'2026-12-01',stock:10,price:50,originalPrice:60,isPurchasable:true});
  await openPurchase;await flush();
  assert.equal(detail.modal.open,false); // A late purchase dialog cannot follow the user.

  const expired=harness('#/profile');
  await flush();
  expired.api.logout=async()=>{expired.setBootstrap(bootstrap(null));const error=new Error('Session expired');error.status=401;throw error;};
  await expired.click('logout');await flush();
  assert.doesNotMatch(expired.main,/alex@example.com/);
  assert.match(expired.main,/欢迎来到 LocalDeal/);
  assert.equal(expired.modal.open,true);assert.match(expired.modal.innerHTML,/登录 LocalDeal/);

  const merchantUser={...user,merchantStoreIds:['s1','s2']},redeemWait=deferred(),redeemCalls=[];
  const merchant=harness('#/merchant',merchantUser,{redeem:input=>{redeemCalls.push(input);return redeemWait.promise;}});
  await flush();
  assert.match(merchant.main,/经营分析/);assert.match(merchant.main,/模拟销售额/);
  const mutation=merchant.submit('redeem-form',{code:'LD-test'});
  assert.equal(merchant.nodes.get('merchant-store').disabled,true);
  merchant.change('merchant-store','s2'); // Pending selection must remain the original branch.
  assert.equal(merchant.nodes.get('merchant-store').value,'s1');
  redeemWait.resolve({storeId:'s1',title:'Test coupon',code:'LD-test'});
  await mutation;await flush();
  assert.equal(redeemCalls[0].storeId,'s1');
  assert.match(merchant.main,/核销成功/);
  assert.equal(merchant.nodes.get('merchant-store').disabled,false);
  console.log('UI state checks passed: stale search/dialogs, hidden own review, expired session and merchant selection.');
})().catch(error=>{console.error(error);process.exitCode=1;});
