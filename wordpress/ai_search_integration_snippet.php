/**
 * Code Snippets (type: PHP, run everywhere).
 * Makes your EXISTING WordPress / WooCommerce product search smart, using Agent 2.
 * No extra page and no shortcode: customers keep using the search bar they already have.
 *
 *   "winter jacket and shoes under 5000"  ->  ranked, budget-aware results
 *
 * Safety net: if the agent is slow, unreachable, or finds nothing, the normal WordPress
 * search runs exactly as before, so search never gets worse than it is today.
 * Needs the catalog sync snippet (so the agent knows your products).
 *
 * Troubleshooting:
 *   - results page: add  &ds_ai_debug=1  to the search URL (admin only) to see what happened
 *   - search box dropdown (AJAX): open  WooCommerce > AI Search Log
 */
if (!defined('DS_AI_SEARCH_TIMEOUT')) {
    define('DS_AI_SEARCH_TIMEOUT', 10);   // seconds to wait for the agent before using normal search
}

// ---------------------------------------------------------------- notes and log
function ds_ai_log($message) {
    $log = get_option('ds_ai_search_log', []);
    if (!is_array($log)) {
        $log = [];
    }
    $log[] = ['t' => time(), 'm' => substr((string) $message, 0, 400)];
    update_option('ds_ai_search_log', array_slice($log, -40), false);
}

function ds_ai_note($message) {
    if (!isset($GLOBALS['ds_ai_debug'])) {
        $GLOBALS['ds_ai_debug'] = [];
    }
    $GLOBALS['ds_ai_debug'][] = $message;
    if (wp_doing_ajax()) {
        ds_ai_log($message);   // AJAX requests have no page to show a banner on, so keep a log
    }
}

// ---------------------------------------------------------------- talk to the agent
function ds_ai_search_ids($text) {
    static $cache = [];
    if (isset($cache[$text])) {
        return $cache[$text];
    }
    $cache[$text] = [];

    // remember good answers for 10 minutes (live typing and the results page then cost nothing)
    $cache_key = 'ds_ai_q_' . md5(strtolower($text) . '|' . (is_user_logged_in() ? get_current_user_id() : 0));
    $cached    = get_transient($cache_key);
    if (is_array($cached) && !empty($cached)) {
        ds_ai_note('served from the 10-minute cache: ' . implode(',', $cached));
        $cache[$text] = $cached;
        return $cache[$text];
    }

    $site_key = defined('DS_AGENTS_SITE_KEY') ? DS_AGENTS_SITE_KEY : '';   // set in the config snippet

    // rate limit: 20 smart searches per minute per visitor (protects your AI quota)
    $ip    = isset($_SERVER['REMOTE_ADDR']) ? sanitize_text_field(wp_unslash($_SERVER['REMOTE_ADDR'])) : 'unknown';
    $rl    = 'ds_ai_rl_' . md5($ip);
    $count = (int) get_transient($rl);
    if ($count >= 20) {
        ds_ai_note('rate limit reached (20 searches per minute)');
        return $cache[$text];
    }
    set_transient($rl, $count + 1, 60);

    $payload = ['query' => $text, 'limit' => 30];
    if (is_user_logged_in() && function_exists('wc_get_orders')) {
        $user   = wp_get_current_user();
        $bought = [];
        $orders = wc_get_orders(['customer_id' => $user->ID, 'limit' => 20, 'status' => ['completed', 'processing']]);
        foreach ($orders as $order) {
            foreach ($order->get_items() as $item) {
                $bought[] = (string) $item->get_product_id();
            }
        }
        $payload['customer_email']        = $user->user_email;
        $payload['purchased_product_ids'] = array_values(array_unique($bought));
    }

    $headers = ['Content-Type' => 'application/json'];
    if ($site_key !== '') {
        $headers['X-Site-Key'] = $site_key;
    }
    $res = wp_remote_post('https://ai-agents-service-tdhq.onrender.com/recommendations', [
        'timeout' => DS_AI_SEARCH_TIMEOUT,
        'headers' => $headers,
        'body'    => wp_json_encode($payload),
    ]);
    if (is_wp_error($res)) {
        ds_ai_note('agent call failed (probably asleep or too slow): ' . $res->get_error_message());
        // start waking the service now, so the NEXT search is fast
        wp_remote_get('https://ai-agents-service-tdhq.onrender.com/health', ['timeout' => 0.01, 'blocking' => false]);
        return $cache[$text];
    }
    if (wp_remote_retrieve_response_code($res) !== 200) {
        ds_ai_note('agent answered HTTP ' . intval(wp_remote_retrieve_response_code($res)) . ': ' . substr(wp_remote_retrieve_body($res), 0, 200));
        return $cache[$text];
    }

    $data = json_decode(wp_remote_retrieve_body($res), true);
    $ids  = [];
    if (is_array($data) && !empty($data['results'])) {
        foreach ($data['results'] as $row) {
            $id = isset($row['id']) ? absint($row['id']) : 0;   // sample products ('sample-1') become 0 and are skipped
            if ($id > 0) {
                $ids[] = $id;
            }
        }
    }
    $found = is_array($data) && isset($data['results']) ? count($data['results']) : 0;
    ds_ai_note('agent returned ' . $found . ' result(s); usable product ids: ' . (empty($ids) ? 'none (has the catalog sync run?)' : implode(',', $ids)));
    $cache[$text] = array_values(array_unique($ids));
    if (!empty($cache[$text])) {
        set_transient($cache_key, $cache[$text], 600);
    }
    return $cache[$text];
}

// ---------------------------------------------------------------- take over product searches
add_action('pre_get_posts', function ($query) {
    $ajax = wp_doing_ajax();
    if (is_admin() && !$ajax) {
        return;   // never touch wp-admin screens
    }
    if (!$query->is_main_query() && !$ajax) {
        return;   // only the main search query, or AJAX live search
    }
    if ($ajax) {
        $ref = function_exists('wp_get_raw_referer') ? wp_get_raw_referer() : '';
        if ($ref && strpos($ref, admin_url()) === 0) {
            return;   // AJAX coming from wp-admin (product pickers etc.)
        }
    }
    if ($query->get('ds_ai_override')) {
        return;
    }

    $text = trim(wp_strip_all_tags((string) $query->get('s')));
    if (strlen($text) < 2 || strlen($text) > 300) {
        return;
    }
    $types = (array) $query->get('post_type');
    if ($ajax) {
        $action = isset($_REQUEST['action']) ? sanitize_key(wp_unslash($_REQUEST['action'])) : '';
        ds_ai_note('AJAX search seen: action=' . $action . ', text="' . $text . '", post_type=' . implode(',', array_map('strval', $types)));
    }
    if (!in_array('product', $types, true)) {
        if ($ajax) {
            ds_ai_note('skipped: this query is not a product query');
        }
        return;   // only product searches
    }

    if ($ajax && strlen($text) < 4) {
        ds_ai_note('skipped: live search text is still too short (waiting for 4+ characters)');
        return;
    }

    ds_ai_note('product search reached the snippet: "' . $text . '"');
    $ids      = ds_ai_search_ids($text);
    $existing = $query->get('post__in');
    if (!empty($existing) && is_array($existing)) {
        $ids = array_values(array_intersect($ids, array_map('absint', $existing)));   // respect other filters
    }
    if (empty($ids)) {
        ds_ai_note('no usable ids, so the normal WordPress search ran');
        return;   // agent had no answer: normal WordPress search runs
    }

    $query->set('post__in', $ids);
    $query->set('orderby', 'post__in');   // keep the agent's ranking
    $query->set('ds_ai_override', true);
    ds_ai_note('agent ranking applied to ' . count($ids) . ' product(s)');
}, 20);

// For those queries, switch off WordPress' own text matching (the agent already did the matching)
add_filter('posts_search', function ($search, $query) {
    return $query->get('ds_ai_override') ? '' : $search;
}, 999, 2);

// ---------------------------------------------------------------- find the theme's live-search AJAX action
add_action('admin_init', function () {
    if (!wp_doing_ajax()) {
        return;
    }
    $ref = function_exists('wp_get_raw_referer') ? wp_get_raw_referer() : '';
    if ($ref && strpos($ref, admin_url()) === 0) {
        return;
    }
    $search_keys = ['s', 'q', 'keyword', 'keywords', 'search', 'query', 'term', 'search_keyword', 'product_name'];
    foreach ($search_keys as $key) {
        if (!empty($_REQUEST[$key]) && is_string($_REQUEST[$key])) {
            $action = isset($_REQUEST['action']) ? sanitize_key(wp_unslash($_REQUEST['action'])) : '(none)';
            $names  = implode(',', array_map('sanitize_key', array_keys($_REQUEST)));
            ds_ai_log('Search-like AJAX request: action=' . $action . ', field "' . $key . '", all fields: ' . $names);
            return;
        }
    }
});

// ---------------------------------------------------------------- troubleshooting views
add_action('wp_footer', function () {
    if (empty($_GET['ds_ai_debug']) || !current_user_can('manage_options')) {
        return;
    }
    $notes = isset($GLOBALS['ds_ai_debug']) ? $GLOBALS['ds_ai_debug'] : ['the snippet is active, but no product search reached it (the URL needs post_type=product)'];
    echo '<div style="position:fixed;bottom:0;left:0;right:0;z-index:99999;background:#111;color:#fff;padding:10px;font:13px monospace">DS-AI DEBUG: ' . esc_html(implode(' | ', $notes)) . '</div>';
});

add_action('admin_menu', function () {
    add_submenu_page('woocommerce', 'AI Search Log', 'AI Search Log', 'manage_options', 'ds-ai-search-log', 'ds_ai_log_page');
});

function ds_ai_log_page() {
    if (!current_user_can('manage_options')) {
        return;
    }
    if (isset($_POST['ds_clear_log']) && check_admin_referer('ds_clear_log')) {
        delete_option('ds_ai_search_log');
    }
    $log = get_option('ds_ai_search_log', []);
    $log = is_array($log) ? array_reverse($log) : [];

    echo '<div class="wrap"><h1>AI Search Log</h1>';
    echo '<p>Type something in your site search box (in another tab), then reload this page. Newest entries first.</p>';
    echo '<form method="post">';
    wp_nonce_field('ds_clear_log');
    submit_button('Clear log', 'secondary', 'ds_clear_log', false);
    echo '</form>';
    if (empty($log)) {
        echo '<p><strong>No entries yet.</strong></p>';
    } else {
        echo '<table class="widefat striped" style="margin-top:12px"><thead><tr><th style="width:90px">Time</th><th>What happened</th></tr></thead><tbody>';
        foreach ($log as $row) {
            echo '<tr><td>' . esc_html(wp_date('H:i:s', $row['t'])) . '</td><td>' . esc_html($row['m']) . '</td></tr>';
        }
        echo '</tbody></table>';
    }
    echo '</div>';
}

// ---------------------------------------------------------------- optional: keep the free Render service awake
add_filter('cron_schedules', function ($schedules) {
    $schedules['ds_ten_minutes'] = ['interval' => 600, 'display' => 'Every 10 minutes'];
    return $schedules;
});
add_action('init', function () {
    if (!wp_next_scheduled('ds_agents_keepwarm')) {
        wp_schedule_event(time() + 120, 'ds_ten_minutes', 'ds_agents_keepwarm');
    }
});
add_action('ds_agents_keepwarm', function () {
    wp_remote_get('https://ai-agents-service-tdhq.onrender.com/health', ['timeout' => 30]);
});
