"""FastAPI contract checks; the legacy transport remains tested independently."""
from pathlib import Path
import tempfile
import unittest

try:
    from fastapi.testclient import TestClient
    from backend.fastapi_app import create_app, ROUTES
except ModuleNotFoundError:
    TestClient=None


@unittest.skipIf(TestClient is None,'Install requirements-dev.txt to test FastAPI')
class FastAPIContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory=tempfile.TemporaryDirectory(prefix='localdeal-asgi-')
        cls.addClassCleanup(cls.directory.cleanup)
        cls.app=create_app(Path(cls.directory.name)/'test.db')

    def client(self):
        return TestClient(self.app,base_url='http://127.0.0.1:8787')

    def login(self, client, email):
        response=client.post('/api/auth/login',json={'email':email,'password':'LocalDealDemo!2026'},headers={'X-LocalDeal-Request':'1'})
        self.assertEqual(response.status_code,200,response.text)
        return {'X-LocalDeal-Request':'1','X-CSRF-Token':response.json()['data']['csrfToken']}

    def test_documented_routes_and_offline_assets(self):
        with self.client() as client:
            self.assertEqual(client.get('/api/health').json()['data']['databaseVersion'],2)
            schema=client.get('/openapi.json').json()
            for method,path,*_ in ROUTES:
                self.assertIn(method.lower(),schema['paths'][path])
            self.assertIn('requestBody',schema['paths']['/api/merchant/coupons/{coupon_id}/stock']['patch'])
            self.assertIn('/docs-assets/swagger-ui-bundle.js',client.get('/docs').text)
            for path in ('/src/i18n.js','/src/http-api.js','/src/app.js','/docs-assets/swagger-ui-bundle.js','/docs-assets/init.js'):
                response=client.get(path)
                self.assertEqual(response.status_code,200)
                self.assertEqual(response.headers['content-type'],'text/javascript; charset=utf-8')
                self.assertEqual(response.headers['x-content-type-options'],'nosniff')
            self.assertEqual(client.get('/docs-assets/swagger-ui.css').headers['content-type'],'text/css; charset=utf-8')
            self.assertEqual(client.get('/api/stores',params={'limit':2}).json()['data']['total'],6)
            self.assertEqual(client.get('/api/state').json()['data']['user'],None)

    def test_validated_inventory_and_session_scope(self):
        with self.client() as owner, self.client() as customer:
            owner_headers=self.login(owner,'harbor.owner@example.com')
            customer_headers=self.login(customer,'alex@example.com')
            stock=owner.get('/api/coupons/c1').json()['data']['stock']
            path='/api/merchant/coupons/c1/stock'
            body={'stock':stock+3,'expectedStock':stock}
            self.assertEqual(customer.patch(path,json=body,headers=customer_headers).status_code,403)
            self.assertEqual(owner.patch(path,json=body,headers={'X-LocalDeal-Request':'1'}).status_code,403)
            self.assertEqual(owner.patch(path,json={'stock':'9','expectedStock':stock},headers=owner_headers).status_code,400)
            self.assertEqual(owner.patch(path,json=body,headers=owner_headers).json()['data']['stock'],stock+3)
            self.assertEqual(owner.patch(path,json=body,headers=owner_headers).status_code,409)
            self.assertEqual(customer.get('/api/coupons/c1').json()['data']['stock'],stock+3)
            self.assertEqual(owner.patch(path,json={'stock':stock,'expectedStock':stock+3},headers=owner_headers).status_code,200)
            self.assertEqual(owner.post('/api/auth/logout',json={},headers=owner_headers).status_code,200)
            self.assertEqual(owner.get('/api/auth/session').json()['data']['user'],None)

    def test_purchase_redeem_and_group_query(self):
        with self.client() as customer,self.client() as owner:
            customer_headers=self.login(customer,'alex@example.com')
            owner_headers=self.login(owner,'harbor.owner@example.com')
            groups=customer.get('/api/group-match',params={'members':'[{"budget":200,"category":""},{"budget":180,"category":"cat-western"}]'})
            self.assertEqual(groups.status_code,200)
            self.assertGreater(groups.json()['data']['total'],0)
            stock=customer.get('/api/coupons/c1').json()['data']['stock']
            purchase={'couponId':'c1','idempotencyKey':'fastapi-contract-one'}
            created=customer.post('/api/orders',json=purchase,headers=customer_headers)
            self.assertEqual(created.status_code,201,created.text)
            order=created.json()['data']
            self.assertEqual(customer.post('/api/orders',json=purchase,headers=customer_headers).json()['data']['id'],order['id'])
            self.assertEqual(customer.get('/api/coupons/c1').json()['data']['stock'],stock-1)
            redeemed=owner.post('/api/orders/redeem',json={'code':order['code'],'storeId':'s1'},headers=owner_headers)
            self.assertEqual(redeemed.status_code,200,redeemed.text)
            self.assertEqual(redeemed.json()['data']['status'],'redeemed')
