/**
 * Code Snippets (type: PHP, run everywhere).
 * Adds the shortcode [ds_ai_search] - a smart search box powered by Agent 2.
 * Try: "winter jacket and shoes under 5000".
 * The browser never sees your SITE_API_KEY: it talks to WordPress, and WordPress talks to the agent.
 */
if (!function_exists('ds_agents_request')) {
    function ds_agents_request($path, $method, $body = null, $blocking = true) {
        $site_key = '';   // paste the SAME value you set as SITE_API_KEY on Render ('' = no key)
        $args = [
            'method'   => $method,
            'timeout'  => $blocking ? 60 : 0.01,
            'blocking' => $blocking,
            'headers'  => ['Content-Type' => 'application/json'],
        ];
        if ($site_key !== '') {
            $args['headers']['X-Site-Key'] = $site_key;
        }
        if ($body !== null) {
            $args['body'] = wp_json_encode($body);
        }
        return wp_remote_request('https://ai-agents-service-tdhq.onrender.com' . $path, $args);
    }
}

function ds_ai_search_ajax() {
    $query = sanitize_text_field(wp_unslash($_POST['q'] ?? ''));
    if (strlen($query) < 2) {
        wp_send_json(['error' => 'Please type what you are looking for.'], 400);
    }

    // simple rate limit: 10 searches per minute per visitor, to protect your AI quota
    $ip    = isset($_SERVER['REMOTE_ADDR']) ? sanitize_text_field(wp_unslash($_SERVER['REMOTE_ADDR'])) : 'unknown';
    $rl    = 'ds_ai_rl_' . md5($ip);
    $count = (int) get_transient($rl);
    if ($count >= 10) {
        wp_send_json(['error' => 'Too many searches. Please wait a minute and try again.'], 429);
    }
    set_transient($rl, $count + 1, 60);

    $payload = ['query' => $query];
    if (is_user_logged_in()) {
        $user = wp_get_current_user();
        $ids  = [];
        $orders = wc_get_orders(['customer_id' => $user->ID, 'limit' => 20, 'status' => ['completed', 'processing']]);
        foreach ($orders as $order) {
            foreach ($order->get_items() as $item) {
                $ids[] = (string) $item->get_product_id();
            }
        }
        $payload['customer_email']        = $user->user_email;
        $payload['purchased_product_ids'] = array_values(array_unique($ids));
    }

    $res = ds_agents_request('/recommendations', 'POST', $payload, true);
    if (is_wp_error($res) || wp_remote_retrieve_response_code($res) !== 200) {
        wp_send_json(['error' => 'Search is unavailable right now. Please try again in a minute.'], 502);
    }
    wp_send_json(json_decode(wp_remote_retrieve_body($res), true));
}
add_action('wp_ajax_ds_ai_search', 'ds_ai_search_ajax');
add_action('wp_ajax_nopriv_ds_ai_search', 'ds_ai_search_ajax');

add_shortcode('ds_ai_search', function () {
    $css = <<<'CSS'
#ds-ai-search{max-width:900px;margin:20px auto}
#ds-ai-search .ds-ai-bar{display:flex;gap:8px}
#ds-ai-search input{flex:1;padding:12px;border:1px solid #ccc;border-radius:6px;font-size:16px}
#ds-ai-search button{padding:12px 20px;border:0;border-radius:6px;background:#0b8fd0;color:#fff;font-size:16px;cursor:pointer}
#ds-ai-search .ds-ai-note{margin:12px 0;color:#555}
#ds-ai-search .ds-ai-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:12px}
#ds-ai-search .ds-ai-card{border:1px solid #e3e3e3;border-radius:8px;padding:10px;background:#fff;display:flex;flex-direction:column;gap:6px}
#ds-ai-search .ds-ai-card img{width:100%;height:140px;object-fit:contain}
#ds-ai-search .ds-ai-price{font-weight:700}
#ds-ai-search small{color:#777}
CSS;

    $js = <<<'JS'
(function () {
  var box = document.getElementById('ds-ai-search');
  if (!box) { return; }
  var input = box.querySelector('input');
  var button = box.querySelector('button');
  var out = box.querySelector('.ds-ai-results');

  function el(tag, text, cls) {
    var e = document.createElement(tag);
    if (text !== undefined && text !== null) { e.textContent = text; }
    if (cls) { e.className = cls; }
    return e;
  }
  function safeUrl(u) { return (typeof u === 'string' && /^https?:\/\//i.test(u)) ? u : ''; }

  async function run() {
    var q = input.value.trim();
    if (q.length < 2) { return; }
    out.textContent = 'Searching...';
    try {
      var fd = new FormData();
      fd.append('action', 'ds_ai_search');
      fd.append('q', q);
      var r = await fetch('__AJAX_URL__', { method: 'POST', body: fd });
      var d = await r.json();
      out.textContent = '';
      if (d.error) { out.appendChild(el('p', d.error)); return; }

      var it = d.interpretation || {};
      var note = 'Showing results for: ' + (it.items || []).join(' + ');
      if (it.max_price) { note += ' (up to Rs ' + Number(it.max_price).toLocaleString() + ')'; }
      if (it.min_price) { note += ' (from Rs ' + Number(it.min_price).toLocaleString() + ')'; }
      out.appendChild(el('div', note, 'ds-ai-note'));

      if (!d.results || !d.results.length) {
        out.appendChild(el('p', 'No matching products found. Try different words or a higher budget.'));
        return;
      }
      var grid = el('div', null, 'ds-ai-grid');
      d.results.forEach(function (p) {
        var card = el('div', null, 'ds-ai-card');
        var img = safeUrl(p.image_url);
        if (img) {
          var i = document.createElement('img');
          i.src = img; i.alt = p.name; i.loading = 'lazy';
          card.appendChild(i);
        }
        var link = safeUrl(p.url);
        var title = link ? document.createElement('a') : el('strong');
        if (link) { title.href = link; }
        title.textContent = p.name;
        card.appendChild(title);
        card.appendChild(el('div', 'Rs ' + Number(p.price).toLocaleString(), 'ds-ai-price'));
        if (p.matched && p.matched.length) { card.appendChild(el('small', p.matched.join(' / '))); }
        grid.appendChild(card);
      });
      out.appendChild(grid);
    } catch (e) {
      out.textContent = 'Sorry, search is unavailable right now.';
    }
  }

  button.addEventListener('click', run);
  input.addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); run(); } });
})();
JS;

    $js = str_replace('__AJAX_URL__', esc_url_raw(admin_url('admin-ajax.php')), $js);

    $html  = '<div id="ds-ai-search"><style>' . $css . '</style>';
    $html .= '<div class="ds-ai-bar"><input type="text" placeholder="Try: winter jacket and shoes under 5000" maxlength="300">';
    $html .= '<button type="button">Search</button></div>';
    $html .= '<div class="ds-ai-results"></div>';
    $html .= '<script>' . $js . '</script></div>';

    return $html;
});
