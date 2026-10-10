/**
 * Code Snippets (type: PHP, run everywhere).
 * Keeps the AI agent's product list in sync with WooCommerce:
 *   - a product is created or edited      -> sent to the agent automatically
 *   - a product is trashed or deleted     -> removed from the agent
 *   - every day (WP-Cron)                 -> full re-sync as a safety net
 *   - WooCommerce > "Sync to AI agents"   -> button for the first full sync
 */
if (!function_exists('ds_agents_request')) {
    function ds_agents_request($path, $method, $body = null, $blocking = true) {
        $site_key = '';   // paste the SAME value you set as SITE_API_KEY on Render ('' = no key)
        $args = [
            'method'   => $method,
            'timeout'  => $blocking ? 60 : 0.01,   // non-blocking calls do not slow down the admin
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

function ds_product_payload($product) {
    $id   = $product->get_id();
    $cats = wp_get_post_terms($id, 'product_cat', ['fields' => 'names']);
    $tags = wp_get_post_terms($id, 'product_tag', ['fields' => 'names']);
    $text = wp_strip_all_tags($product->get_short_description() ?: $product->get_description());
    $text = trim($text . ' ' . (is_wp_error($tags) ? '' : implode(' ', $tags)));
    $img  = $product->get_image_id() ? wp_get_attachment_image_url($product->get_image_id(), 'woocommerce_thumbnail') : '';

    return [
        'external_id' => (string) $id,
        'name'        => wp_html_excerpt($product->get_name(), 190),
        'price'       => (float) $product->get_price(),
        'category'    => is_wp_error($cats) ? '' : wp_html_excerpt(implode(', ', $cats), 290),
        'description' => wp_html_excerpt($text, 900),
        'url'         => (string) get_permalink($id),
        'image_url'   => $img ? $img : '',
        'in_stock'    => (bool) $product->is_in_stock(),
    ];
}

function ds_sync_one_product($product_id) {
    $product = wc_get_product($product_id);
    if (!$product) {
        return;
    }
    if ($product->get_status() !== 'publish') {
        ds_delete_synced_product($product_id);
        return;
    }
    ds_agents_request('/catalog/products', 'POST', ['products' => [ds_product_payload($product)]], false);
}

function ds_delete_synced_product($product_id) {
    ds_agents_request('/catalog/products/' . intval($product_id), 'DELETE', null, false);
}

function ds_sync_all_products() {
    if (function_exists('set_time_limit')) {
        @set_time_limit(300);
    }
    $page  = 1;
    $total = 0;
    $errors = 0;
    do {
        $products = wc_get_products(['status' => 'publish', 'limit' => 50, 'page' => $page]);
        if (empty($products)) {
            break;
        }
        $batch = [];
        foreach ($products as $product) {
            $batch[] = ds_product_payload($product);
        }
        $res = ds_agents_request('/catalog/products', 'POST', ['products' => $batch], true);
        if (is_wp_error($res) || wp_remote_retrieve_response_code($res) !== 200) {
            $errors++;
        } else {
            $total += count($batch);
        }
        $page++;
    } while (count($products) === 50);

    return [$total, $errors];
}

// New or edited product
add_action('woocommerce_new_product', 'ds_sync_one_product', 20, 1);
add_action('woocommerce_update_product', 'ds_sync_one_product', 20, 1);

// Trashed or deleted product
add_action('wp_trash_post', function ($post_id) {
    if (get_post_type($post_id) === 'product') {
        ds_delete_synced_product($post_id);
    }
});
add_action('before_delete_post', function ($post_id) {
    if (get_post_type($post_id) === 'product') {
        ds_delete_synced_product($post_id);
    }
});

// Daily safety-net sync
add_action('init', function () {
    if (!wp_next_scheduled('ds_agents_daily_sync')) {
        wp_schedule_event(time() + 300, 'daily', 'ds_agents_daily_sync');
    }
});
add_action('ds_agents_daily_sync', 'ds_sync_all_products');

// WooCommerce > Sync to AI agents (button for the first full sync)
add_action('admin_menu', function () {
    add_submenu_page('woocommerce', 'Sync to AI agents', 'Sync to AI agents', 'manage_woocommerce', 'ds-agents-sync', 'ds_agents_sync_page');
});

function ds_agents_sync_page() {
    $notice = '';
    if (isset($_POST['ds_sync_now']) && check_admin_referer('ds_sync_all')) {
        list($ok, $errors) = ds_sync_all_products();
        $notice = '<div class="notice notice-success"><p>Synced ' . intval($ok) . ' products. Batches with errors: ' . intval($errors) . '.</p></div>';
    }
    echo '<div class="wrap"><h1>Sync products to AI agents</h1>' . $notice;
    echo '<p>New and edited products sync automatically. Use this button for the first full sync (it can take a minute if the agent service is asleep).</p>';
    echo '<form method="post">';
    wp_nonce_field('ds_sync_all');
    submit_button('Sync all products now', 'primary', 'ds_sync_now');
    echo '</form></div>';
}
