/* Local-only Swagger UI. Keep the application's same-origin and CSRF rules. */
window.ui = SwaggerUIBundle({
  url: '/openapi.json', dom_id: '#swagger-ui', layout: 'BaseLayout',
  presets: [SwaggerUIBundle.presets.apis], validatorUrl: null,
  requestInterceptor: async function (request) {
    const url = new URL(request.url, location.origin);
    if (url.origin !== location.origin) throw new Error('Only the local API can be called.');
    if (['POST', 'PATCH', 'DELETE'].includes(String(request.method).toUpperCase())) {
      request.headers = request.headers || {};
      request.headers['X-LocalDeal-Request'] = '1';
      if (!['/api/auth/login', '/api/auth/register'].includes(url.pathname)) {
        const response = await fetch('/api/auth/session', { credentials: 'same-origin', cache: 'no-store' });
        const session = await response.json();
        if (session.data?.csrfToken) request.headers['X-CSRF-Token'] = session.data.csrfToken;
      }
    }
    return request;
  }
});
