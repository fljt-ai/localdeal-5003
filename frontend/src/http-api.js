/* Same-origin HTTP adapter. Credentials stay in server-managed session cookies;
   passwords and CSRF tokens are never stored in localStorage. */
(function (root) {
  'use strict';
  let csrfToken = null;
  let authGeneration = 0, requestSerial = 0, tokenSerial = 0;
  const listURL = function (path, values) {
    const query = new URLSearchParams();
    Object.entries(values || {}).forEach(function ([key, value]) {
      if (value !== undefined && value !== null && value !== '') query.set(key, String(value));
    });
    const encoded = query.toString();
    return path + (encoded ? '?' + encoded : '');
  };

  async function request(url, method, body) {
    const authChange = method === 'POST' && ['/api/auth/login', '/api/auth/register', '/api/auth/logout'].includes(url);
    const generation = authChange ? ++authGeneration : authGeneration;
    const serial = ++requestSerial;
    const controller = new AbortController();
    const timeout = setTimeout(function () { controller.abort(); }, 15000);
    const headers = { Accept: 'application/json' };
    const write = method !== 'GET';
    if (write) {
      headers['Content-Type'] = 'application/json';
      headers['X-LocalDeal-Request'] = '1';
      if (csrfToken) headers['X-CSRF-Token'] = csrfToken;
    }
    try {
      const response = await fetch(url, {
        method: method,
        credentials: 'same-origin',
        headers: headers,
        signal: controller.signal,
        cache: 'no-store',
        ...(write ? { body: JSON.stringify(body || {}) } : {})
      });
      let payload;
      try { payload = await response.json(); }
      catch (parseError) { throw new Error('本地服务返回了无法读取的数据，请稍后重试。'); }
      if (!response.ok || payload.error) {
        const problem = new Error(payload.error?.message || '操作未完成，请重试。');
        problem.code = payload.error?.code || 'HTTP_ERROR';
        problem.status = response.status;
        if (response.status === 401 && generation === authGeneration && serial >= tokenSerial) {
          csrfToken = null; tokenSerial = serial;
        }
        throw problem;
      }
      if (!Object.prototype.hasOwnProperty.call(payload, 'data')) throw new Error('本地服务的数据格式不正确，请重试。');
      const data = payload.data;
      if (generation === authGeneration) {
        if (authChange) {
          // Also invalidate reads started while authentication was in flight.
          ++authGeneration; tokenSerial = serial;
          if (url === '/api/auth/logout') csrfToken = null;
          else if (data && Object.prototype.hasOwnProperty.call(data, 'csrfToken')) csrfToken = data.csrfToken || null;
        } else if (serial >= tokenSerial && data && Object.prototype.hasOwnProperty.call(data, 'csrfToken')) {
          csrfToken = data.csrfToken || null; tokenSerial = serial;
        }
      }
      return data;
    } catch (problem) {
      if (problem.name === 'AbortError') {
        const timeoutError = new Error('连接本地服务超时，请重试。');
        timeoutError.code = 'NETWORK_ERROR';
        throw timeoutError;
      }
      if (problem instanceof TypeError) {
        const connectionError = new Error('无法连接本地服务，请确认 LocalDeal 已启动后重试。');
        connectionError.code = 'NETWORK_ERROR';
        throw connectionError;
      }
      throw problem;
    } finally { clearTimeout(timeout); }
  }

  root.LocalDealAPI = Object.freeze({
    getState: function () { return request('/api/state', 'GET'); },
    getSession: function () { return request('/api/auth/session', 'GET'); },
    getStores: function (query) { return request(listURL('/api/stores', query), 'GET'); },
    getStore: function (id) { return request('/api/stores/' + encodeURIComponent(id), 'GET'); },
    getCoupons: function (query) { return request(listURL('/api/coupons', query), 'GET'); },
    getCoupon: function (id) { return request('/api/coupons/' + encodeURIComponent(id), 'GET'); },
    getStoreReviews: function (id, query) { return request(listURL('/api/stores/' + encodeURIComponent(id) + '/reviews', query), 'GET'); },
    getMyReviews: function (query) { return request(listURL('/api/users/me/reviews', query), 'GET'); },
    getMyFavorites: function (query) { return request(listURL('/api/users/me/favorites', query), 'GET'); },
    getOrders: function (query) { return request(listURL('/api/orders', query), 'GET'); },
    getMerchantOrders: function (query) { return request(listURL('/api/merchant/orders', query), 'GET'); },
    getOrderStatus: function (order) { return order.status; },
    subscribe: function () { return function () {}; },
    login: function (input) { return request('/api/auth/login', 'POST', { email: input.email, password: input.password }); },
    register: function (input) { return request('/api/auth/register', 'POST', { name: input.name, email: input.email, password: input.password }); },
    logout: function () { return request('/api/auth/logout', 'POST', {}); },
    updateProfile: function (input) { return request('/api/users/me', 'PATCH', { name: input.name }); },
    toggleFavorite: function (storeId) { return request('/api/favorites/toggle', 'POST', { storeId: storeId }); },
    saveReview: function (input) {
      return input.id
        ? request('/api/reviews/' + encodeURIComponent(input.id), 'PATCH', { rating: input.rating, comment: input.comment })
        : request('/api/stores/' + encodeURIComponent(input.storeId) + '/reviews', 'POST', { rating: input.rating, comment: input.comment });
    },
    deleteReview: function (id) { return request('/api/reviews/' + encodeURIComponent(id), 'DELETE', {}); },
    purchase: function (couponId, idempotencyKey) {
      if (!idempotencyKey) return Promise.reject(new Error('购买请求缺少订单标识，请重新打开购买窗口。'));
      return request('/api/orders', 'POST', { couponId: couponId, idempotencyKey: idempotencyKey });
    },
    redeem: function (input) { return request('/api/orders/redeem', 'POST', { code: input.code, storeId: input.storeId }); },
    exportData: function () { return request('/api/export', 'GET'); }
  });
})(window);
