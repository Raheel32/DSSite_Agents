/**
 * Code Snippets (type: PHP, run everywhere).
 * Adds  WooCommerce > "AI Price Audit"  (Agent 3).
 * Pick a product, click Audit: the agent searches Pakistani stores for the same product, a reviewer
 * checks the prices, and you get a SUGGESTION (lower / raise / keep) with the competitor prices as proof.
 * Nothing changes by itself. You press "Apply this price" yourself if you agree.
 * Needs the config snippet (DS_AGENTS_ADMIN_KEY).
 */
function ds_pa_api($path, $method = 'GET', $body = null, $timeout = 60) {
    $admin_key = defined('DS_AGENTS_ADMIN_KEY') ? DS_AGENTS_ADMIN_KEY : '';   // set in the config snippet
    $args = [
        'method'  => $method,
        'timeout' => $timeout,
        'headers' => ['Content-Type' => 'application/json', 'X-Admin-Key' => $admin_key],
    ];
    if ($body !== null) {
        $args['body'] = wp_json_encode($body);
    }
    $res = wp_remote_request('https://ai-agents-service-tdhq.onrender.com' . $path, $args);
    if (is_wp_error($res)) {
        return [0, null, $res->get_error_message()];
    }
    $raw = wp_remote_retrieve_body($res);
    return [wp_remote_retrieve_response_code($res), json_decode($raw, true), $raw];
}

function ds_pa_notice($type, $text) {
    return '<div class="notice notice-' . esc_attr($type) . '"><p>' . esc_html($text) . '</p></div>';
}

function ds_pa_error_text($code, $data, $raw) {
    if ($code === 0) {
        return 'Could not reach the agent service: ' . $raw;
    }
    if ($code === 401) {
        return 'The agent service refused the key. Check DS_AGENTS_ADMIN_KEY in the config snippet.';
    }
    if (is_array($data) && isset($data['detail']) && is_string($data['detail'])) {
        return $data['detail'];
    }
    return 'Unexpected answer (HTTP ' . intval($code) . ').';
}

// Every product, and every variation of variable products (your pack sizes), as options for the dropdown
function ds_pa_product_options() {
    $options  = [];
    $products = wc_get_products(['status' => 'publish', 'limit' => 150, 'orderby' => 'title', 'order' => 'ASC']);
    foreach ($products as $product) {
        if ($product->is_type('variable')) {
            foreach ($product->get_children() as $variation_id) {
                $variation = wc_get_product($variation_id);
                if ($variation && $variation->get_price() !== '') {
                    $options[] = [$variation->get_id(), $variation->get_name(), (float) $variation->get_price()];
                }
            }
        } elseif ($product->get_price() !== '') {
            $options[] = [$product->get_id(), $product->get_name(), (float) $product->get_price()];
        }
    }
    return $options;
}

function ds_pa_handle_audit() {
    $product = wc_get_product(absint($_POST['product_id'] ?? 0));
    if (!$product || $product->get_price() === '') {
        return ds_pa_notice('error', 'Please choose a product that has a price.');
    }
    $body = [
        'product_id'      => (string) $product->get_id(),
        'name'            => $product->get_name(),
        'our_price'       => (float) $product->get_price(),
        'exclude_domains' => [(string) wp_parse_url(home_url(), PHP_URL_HOST)],
    ];
    $min = isset($_POST['min_price']) ? (float) $_POST['min_price'] : 0;
    if ($min > 0) {
        $body['min_price'] = $min;
    }
    list($code, $data, $raw) = ds_pa_api('/pricing/audit', 'POST', $body, 120);
    if ($code !== 200 || !is_array($data)) {
        return ds_pa_notice('error', ds_pa_error_text($code, $data, $raw));
    }
    return ds_pa_notice('success', 'Audit finished for ' . $product->get_name() . ' after ' . intval($data['iterations']) . ' search round(s). See the table below.');
}

function ds_pa_handle_apply() {
    $product = wc_get_product(absint($_POST['product_id'] ?? 0));
    $new     = isset($_POST['new_price']) ? (float) $_POST['new_price'] : 0;
    $audit   = absint($_POST['audit_id'] ?? 0);
    if (!$product || $new <= 0) {
        return ds_pa_notice('error', 'That product or price is not valid.');
    }
    if ($product->get_sale_price() !== '') {
        return ds_pa_notice('error', 'This product has a sale price. Please change its price by hand so the sale is not broken.');
    }
    $current = (float) $product->get_regular_price();
    if ($current > 0 && abs($new - $current) / $current > 0.30) {
        return ds_pa_notice('error', 'The new price differs from the current price by more than 30%. Please change it by hand.');
    }
    $product->set_regular_price((string) $new);
    $product->save();
    if ($product->is_type('variation')) {
        WC_Product_Variable::sync($product->get_parent_id());
        wc_delete_product_transients($product->get_parent_id());
    }
    if ($audit > 0) {
        ds_pa_api('/pricing/audits/' . $audit . '/status', 'POST', ['status' => 'applied']);
    }
    return ds_pa_notice('success', 'Price updated: ' . $product->get_name() . ' is now Rs ' . number_format($new) . '.');
}

function ds_pa_handle_dismiss() {
    $audit = absint($_POST['audit_id'] ?? 0);
    if ($audit > 0) {
        ds_pa_api('/pricing/audits/' . $audit . '/status', 'POST', ['status' => 'dismissed']);
    }
    return ds_pa_notice('success', 'Suggestion dismissed.');
}

function ds_pa_badge($suggestion) {
    $colors = ['lower' => '#f7c5c5', 'raise' => '#c8f2d0', 'keep' => '#e5e5e5', 'no_data' => '#ffe08a'];
    $bg = isset($colors[$suggestion]) ? $colors[$suggestion] : '#e5e5e5';
    return '<span style="padding:2px 8px;border-radius:10px;background:' . esc_attr($bg) . '">' . esc_html($suggestion) . '</span>';
}

function ds_pa_row($a) {
    $offers = '<details><summary>' . count((array) $a['offers']) . ' competitor price(s)</summary><ul style="margin:6px 0 0 16px;list-style:disc">';
    foreach ((array) $a['offers'] as $offer) {
        $offers .= '<li><a href="' . esc_url($offer['url']) . '" target="_blank" rel="noopener noreferrer">' . esc_html($offer['store']) . '</a>: Rs '
                 . esc_html(number_format((float) $offer['price'])) . '</li>';
    }
    $offers .= '</ul><p style="margin:6px 0 0"><em>What the agent did:</em></p><ol style="margin:4px 0 0 16px">';
    foreach ((array) $a['steps'] as $step) {
        $offers .= '<li>' . esc_html($step) . '</li>';
    }
    $offers .= '</ol></details>';

    $action = '';
    $can_apply = in_array($a['suggestion'], ['lower', 'raise'], true) && $a['status'] === 'suggested' && !empty($a['product_id']) && $a['suggested_price'] !== null;
    if ($can_apply) {
        $action  = '<form method="post" style="display:inline-block;margin-right:6px">';
        $action .= wp_nonce_field('ds_pa_apply', '_wpnonce', true, false);
        $action .= '<input type="hidden" name="audit_id" value="' . intval($a['audit_id']) . '">';
        $action .= '<input type="hidden" name="product_id" value="' . esc_attr($a['product_id']) . '">';
        $action .= '<input type="hidden" name="new_price" value="' . esc_attr($a['suggested_price']) . '">';
        $action .= '<button class="button button-primary" name="ds_pa_apply" value="1" onclick="return confirm(\'Change the price to Rs ' . esc_js(number_format((float) $a['suggested_price'])) . '?\');">Apply this price</button></form>';
        $action .= '<form method="post" style="display:inline-block">';
        $action .= wp_nonce_field('ds_pa_dismiss', '_wpnonce', true, false);
        $action .= '<input type="hidden" name="audit_id" value="' . intval($a['audit_id']) . '">';
        $action .= '<button class="button" name="ds_pa_dismiss" value="1">Dismiss</button></form>';
    }
    $suggested = $a['suggested_price'] === null ? '-' : 'Rs ' . number_format((float) $a['suggested_price']);

    return '<tr><td>' . esc_html($a['name']) . '</td><td>Rs ' . esc_html(number_format((float) $a['our_price'])) . '</td><td>'
         . ds_pa_badge($a['suggestion']) . '</td><td>' . esc_html($suggested) . '</td><td>' . esc_html($a['confidence']) . '</td><td>'
         . esc_html($a['summary']) . $offers . '</td><td>' . esc_html($a['status']) . '</td><td>' . $action . '</td></tr>';
}

add_action('admin_menu', function () {
    add_submenu_page('woocommerce', 'AI Price Audit', 'AI Price Audit', 'edit_products', 'ds-agents-price-audit', 'ds_pa_page');
});

function ds_pa_page() {
    if (!current_user_can('edit_products')) {
        return;
    }
    $notice = '';
    if (isset($_POST['ds_pa_audit']) && check_admin_referer('ds_pa_audit')) {
        $notice = ds_pa_handle_audit();
    } elseif (isset($_POST['ds_pa_apply']) && check_admin_referer('ds_pa_apply')) {
        $notice = ds_pa_handle_apply();
    } elseif (isset($_POST['ds_pa_dismiss']) && check_admin_referer('ds_pa_dismiss')) {
        $notice = ds_pa_handle_dismiss();
    }

    echo '<div class="wrap"><h1>AI Price Audit</h1>' . $notice;
    echo '<p>Pick a product and click <strong>Audit</strong>. The agent looks for the same product (same pack size) in Pakistani online stores and suggests whether to lower, raise or keep your price. It can take up to a minute. Prices found on the web can be old, so always glance at the competitor links.</p>';

    echo '<form method="post" style="margin:16px 0">';
    wp_nonce_field('ds_pa_audit');
    echo '<select name="product_id" required style="min-width:380px"><option value="">Choose a product or pack size...</option>';
    foreach (ds_pa_product_options() as $opt) {
        echo '<option value="' . intval($opt[0]) . '">' . esc_html($opt[1] . ' - Rs ' . number_format($opt[2])) . '</option>';
    }
    echo '</select> ';
    echo '<input type="number" name="min_price" min="0" step="1" placeholder="Lowest price I accept (optional)" style="width:230px"> ';
    submit_button('Audit this product', 'primary', 'ds_pa_audit', false);
    echo '</form>';

    list($code, $audits, $raw) = ds_pa_api('/pricing/audits?limit=15');
    echo '<h2>Recent audits</h2>';
    if ($code !== 200 || !is_array($audits)) {
        echo ds_pa_notice('error', ds_pa_error_text($code, $audits, $raw));
    } elseif (empty($audits)) {
        echo '<p>No audits yet.</p>';
    } else {
        echo '<table class="widefat striped"><thead><tr><th>Product</th><th>Your price</th><th>Suggestion</th><th>Suggested price</th><th>Confidence</th><th>Why</th><th>Status</th><th>Action</th></tr></thead><tbody>';
        foreach ($audits as $a) {
            echo ds_pa_row($a);
        }
        echo '</tbody></table>';
    }
    echo '</div>';
}
