// Dependency-free adapter contract check. Run: node frontend/tests/http-api.test.js
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const calls = [];
let nextPayload = {data:{items:[],total:0,limit:12,offset:0,hasMore:false}};
let nextStatus = 200;
let networkFailure = false;
let holdResponse = false, releaseHeld;
const sandbox = {
  window:{}, AbortController, URLSearchParams, TypeError, setTimeout, clearTimeout,
  fetch:async (url,options) => {
    calls.push({url,options});
    if(networkFailure){networkFailure=false;throw new TypeError('offline');}
    const payload=nextPayload,status=nextStatus;
    if(holdResponse){holdResponse=false;await new Promise(resolve=>{releaseHeld=resolve;});}
    return {ok:status>=200&&status<300,status,json:async()=>payload};
  }
};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../src/http-api.js'),'utf8'),sandbox);
const api=sandbox.window.LocalDealAPI;
const last=()=>calls.at(-1);
(async()=>{
  nextPayload={data:{csrfToken:'test-csrf',summary:{favorites:100,reviews:100,orders:{all:100}}}};
  await api.getState();
  assert.equal(last().url,'/api/state');
  const methods=[
    ['getStores',[{q:'汉堡 & coffee',district:'d1',category:'cat1',couponOnly:true,sort:'rating',limit:12,offset:24}],'/api/stores'],
    ['getCoupons',[{storeId:'s1',limit:12,offset:12}],'/api/coupons'],
    ['getMyReviews',[{limit:10,offset:20}],'/api/users/me/reviews'],
    ['getMyFavorites',[{limit:12,offset:12}],'/api/users/me/favorites'],
    ['getOrders',[{status:'expired',limit:10,offset:10}],'/api/orders'],
    ['getMerchantOrders',[{storeId:'s2',status:'redeemed',limit:10,offset:20}],'/api/merchant/orders'],
    ['getMerchantAnalytics',[{storeId:'s2',days:7}],'/api/merchant/analytics']
  ];
  nextPayload={data:{items:[],total:99,limit:10,offset:20,hasMore:true}};
  for(const [method,args,route]of methods) {
    const data=await api[method](...args),parsed=new URL(last().url,'http://127.0.0.1');
    assert.equal(parsed.pathname,route);
    for(const [key,value]of Object.entries(args[0]))assert.equal(parsed.searchParams.get(key),String(value));
    assert.equal(data.total,99);
    assert.equal(last().options.method,'GET');
    assert.equal(last().options.credentials,'same-origin');
    assert.equal(last().options.cache,'no-store');
    assert.equal(last().options.headers['X-CSRF-Token'],undefined);
  }
  await api.getStoreReviews('branch/一',{rating:5,sort:'new',limit:10,offset:30});
  const members=[{budget:100,category:'cat-coffee'},{budget:120,category:''}];
  await api.getGroupMatch({members,district:'central',limit:12,offset:0});
  const grouping=new URL(last().url,'http://127.0.0.1');
  assert.equal(grouping.pathname,'/api/group-match');assert.deepEqual(JSON.parse(grouping.searchParams.get('members')),members);
  await api.getStoreReviews('branch/一',{rating:5,sort:'new',limit:10,offset:30});
  assert.equal(last().url,'/api/stores/branch%2F%E4%B8%80/reviews?rating=5&sort=new&limit=10&offset=30');
  await api.getStore('branch/一');assert.equal(last().url,'/api/stores/branch%2F%E4%B8%80');
  await api.getCoupon('coupon/一');assert.equal(last().url,'/api/coupons/coupon%2F%E4%B8%80');
  nextPayload={data:{id:'order-a',status:'unused'}};
  networkFailure=true;
  await assert.rejects(api.purchase('c1','same-intent-key'),error=>error.code==='NETWORK_ERROR');
  const firstBody=last().options.body;
  await api.purchase('c1','same-intent-key');
  assert.equal(last().options.body,firstBody);
  assert.equal(last().options.headers['X-CSRF-Token'],'test-csrf');
  assert.equal(last().options.headers['X-LocalDeal-Request'],'1');
  assert.equal(last().options.headers['Content-Type'],'application/json');
  await assert.rejects(api.purchase('c1'),/订单标识/);
  assert.equal(api.getOrderStatus({status:'expired'}),'expired');
  nextPayload={error:{code:'AUTH_REQUIRED',message:'请登录'}};nextStatus=401;
  await assert.rejects(api.getOrders({limit:10}),error=>error.code==='AUTH_REQUIRED'&&error.status===401);
  nextPayload={data:{user:null}};nextStatus=200;
  await api.login({email:'alex@example.com',password:'demo'});
  assert.equal(last().options.headers['X-CSRF-Token'],undefined);
  assert.deepEqual(JSON.parse(last().options.body),{email:'alex@example.com',password:'demo'});
  // Old state responses and old 401s must not overwrite a newly logged-in token.
  nextPayload={data:{csrfToken:'old-session-token'}};holdResponse=true;
  const oldState=api.getState();
  nextPayload={data:{user:{id:'new-user'},csrfToken:'new-session-token'}};
  await api.login({email:'new@example.com',password:'demo'});
  releaseHeld();await oldState;
  nextPayload={data:{isFavorite:true}};
  await api.toggleFavorite('s1');
  assert.equal(last().options.headers['X-CSRF-Token'],'new-session-token');
  nextPayload={error:{code:'AUTH_REQUIRED',message:'old expired session'}};nextStatus=401;holdResponse=true;
  const oldOrders=api.getOrders({limit:10}).catch(error=>error);
  nextPayload={data:{user:{id:'latest-user'},csrfToken:'latest-session-token'}};nextStatus=200;
  await api.login({email:'latest@example.com',password:'demo'});
  releaseHeld();assert.equal((await oldOrders).status,401);
  nextPayload={data:{isFavorite:false}};
  await api.toggleFavorite('s1');
  assert.equal(last().options.headers['X-CSRF-Token'],'latest-session-token');
  // A guest read started during login is also stale after authentication succeeds.
  nextPayload={data:{user:{id:'during-login'},csrfToken:'during-login-token'}};holdResponse=true;
  const heldLogin=api.login({email:'during@example.com',password:'demo'});
  const releaseLogin=releaseHeld;
  nextPayload={data:{user:null,csrfToken:null}};holdResponse=true;
  const duringState=api.getState(),releaseState=releaseHeld;
  releaseLogin();await heldLogin;
  releaseState();await duringState;
  nextPayload={data:{isFavorite:true}};
  await api.toggleFavorite('s1');
  assert.equal(last().options.headers['X-CSRF-Token'],'during-login-token');
  console.log('HTTP adapter pagination, encoding, session generations and purchase retry checks passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
