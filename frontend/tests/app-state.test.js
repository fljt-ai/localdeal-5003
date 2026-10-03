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
function harness(initialHash='#/discover',person=user,overrides={}) {
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
    getStore:async id=>store(id,id==='s2'?'Second store':'Test store'),
    getCoupons:async()=>paged([]),
    getCoupon:async()=>({id:'c1',storeId:'s1',title:'Test coupon',terms:[],expiresAt:'2026-12-01',stock:10,price:50,originalPrice:60,isPurchasable:true}),
    getStoreReviews:async()=>({...paged([],0,10),ownReview:null}),
    getMyFavorites:async()=>paged([store()]),
    getMyReviews:async()=>paged([],0,10),
    getOrders:async()=>paged([],0,10),
    getMerchantOrders:async()=>paged([],0,10),
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
  vm.runInNewContext(source,sandbox);
  return {
    api,document,calls,nodes,
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
