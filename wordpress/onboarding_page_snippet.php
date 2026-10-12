/**
 * Code Snippets (type: PHP, run everywhere).
 * Adds  WooCommerce > "AI Product Onboarding"  (Agent 5).
 * The vendor uploads ONE photo and types the product name. The agent writes the description,
 * SEO title and meta description, tags and category, and this page creates a DRAFT product
 * (never published automatically) so a person can review it first.
 * Needs the config snippet (SITE_API_KEY). Price and stock are left for you to fill in.
 */
function ds_onboarding_error($text) {
    return '<div class="notice notice-error"><p>' . esc_html($text) . '</p></div>';
}

// Shrink the photo before sending it to the AI (faster, cheaper, and stays under the 4 MB limit)
function ds_onboarding_prepare_image($path, $mime) {
    $editor = wp_get_image_editor($path);
    if (!is_wp_error($editor)) {
        $editor->resize(1024, 1024, false);
        $editor->set_quality(80);
        $out   = trailingslashit(get_temp_dir()) . 'ds-onboard-' . wp_generate_password(12, false) . '.jpg';
        $saved = $editor->save($out, 'image/jpeg');
        if (!is_wp_error($saved) && !empty($saved['path']) && file_exists($saved['path'])) {
            $bytes = file_get_contents($saved['path']);
            @unlink($saved['path']);
            if ($bytes !== false && strlen($bytes) > 0) {
                return [base64_encode($bytes), 'image/jpeg'];
            }
        }
    }
    // no image editor available: send the original if it is small enough
    $size = filesize($path);
    if ($size !== false && $size <= 4 * 1024 * 1024) {
        return [base64_encode(file_get_contents($path)), $mime];
    }
    return null;
}

function ds_onboarding_handle() {
    $name = sanitize_text_field(wp_unslash($_POST['product_name'] ?? ''));
    if (strlen($name) < 2) {
        return ds_onboarding_error('Please type the product name.');
    }
    if (empty($_FILES['image']['tmp_name']) || !empty($_FILES['image']['error'])) {
        return ds_onboarding_error('Please choose a photo to upload.');
    }
    $file = $_FILES['image'];
    if ($file['size'] > 10 * 1024 * 1024) {
        return ds_onboarding_error('The photo is larger than 10 MB. Please choose a smaller one.');
    }
    $allowed = ['jpg|jpeg|jpe' => 'image/jpeg', 'png' => 'image/png', 'webp' => 'image/webp'];
    $check   = wp_check_filetype_and_ext($file['tmp_name'], $file['name'], $allowed);
    if (empty($check['type'])) {
        return ds_onboarding_error('Please upload a JPG, PNG or WebP image.');
    }
    $prepared = ds_onboarding_prepare_image($file['tmp_name'], $check['type']);
    if (!$prepared) {
        return ds_onboarding_error('Could not prepare the photo. Please try a smaller image.');
    }

    $terms = get_terms(['taxonomy' => 'product_cat', 'hide_empty' => false, 'fields' => 'names']);
    $cats  = [];
    if (!is_wp_error($terms)) {
        foreach ($terms as $term_name) {
            if (strtolower($term_name) !== 'uncategorized') {
                $cats[] = $term_name;
            }
        }
    }

    $site_key = defined('DS_AGENTS_SITE_KEY') ? DS_AGENTS_SITE_KEY : '';   // set in the config snippet
    $headers  = ['Content-Type' => 'application/json'];
    if ($site_key !== '') {
        $headers['X-Site-Key'] = $site_key;
    }
    $res = wp_remote_post('https://ai-agents-service-tdhq.onrender.com/onboarding/product', [
        'timeout' => 120,   // the AI may need a minute, plus a cold start
        'headers' => $headers,
        'body'    => wp_json_encode([
            'name'         => $name,
            'image_base64' => $prepared[0],
            'mime_type'    => $prepared[1],
            'categories'   => $cats,
        ]),
    ]);
    if (is_wp_error($res)) {
        return ds_onboarding_error('Could not reach the AI service: ' . $res->get_error_message());
    }
    $code = wp_remote_retrieve_response_code($res);
    $data = json_decode(wp_remote_retrieve_body($res), true);
    if ($code === 401) {
        return ds_onboarding_error('The AI service refused the key. Check DS_AGENTS_SITE_KEY in the config snippet.');
    }
    if ($code !== 200 || !is_array($data) || empty($data['title'])) {
        return ds_onboarding_error('The AI service could not process this product (HTTP ' . intval($code) . ').');
    }

    require_once ABSPATH . 'wp-admin/includes/file.php';
    require_once ABSPATH . 'wp-admin/includes/image.php';
    require_once ABSPATH . 'wp-admin/includes/media.php';
    $attachment_id = media_handle_upload('image', 0);
    if (is_wp_error($attachment_id)) {
        $attachment_id = 0;
    }

    $product = new WC_Product_Simple();
    $product->set_name(sanitize_text_field($data['title']));
    $product->set_status('draft');                       // a person reviews it before it goes live
    $product->set_short_description(wp_kses_post($data['short_description']));
    $product->set_description(wp_kses_post(wpautop($data['description'])));
    if ($attachment_id) {
        $product->set_image_id($attachment_id);
    }
    $term = get_term_by('name', $data['category'], 'product_cat');
    if ($term && !is_wp_error($term)) {
        $product->set_category_ids([(int) $term->term_id]);
    }
    $tag_ids = [];
    foreach ((array) $data['tags'] as $tag_name) {
        $tag_name = sanitize_text_field($tag_name);
        if ($tag_name === '') {
            continue;
        }
        $existing = term_exists($tag_name, 'product_tag');
        if (!$existing) {
            $existing = wp_insert_term($tag_name, 'product_tag');
        }
        if (!is_wp_error($existing)) {
            $tag_ids[] = (int) (is_array($existing) ? $existing['term_id'] : $existing);
        }
    }
    $product->set_tag_ids($tag_ids);
    $product_id = $product->save();

    // SEO plugin fields (harmless if you use a different SEO plugin)
    $seo_title = sanitize_text_field($data['seo_title']);
    $meta_desc = sanitize_text_field($data['meta_description']);
    $focus_kw  = sanitize_text_field($data['focus_keyword']);
    update_post_meta($product_id, '_yoast_wpseo_title', $seo_title);
    update_post_meta($product_id, '_yoast_wpseo_metadesc', $meta_desc);
    update_post_meta($product_id, '_yoast_wpseo_focuskw', $focus_kw);
    update_post_meta($product_id, 'rank_math_title', $seo_title);
    update_post_meta($product_id, 'rank_math_description', $meta_desc);
    update_post_meta($product_id, 'rank_math_focus_keyword', $focus_kw);

    $edit_url = admin_url('post.php?post=' . intval($product_id) . '&action=edit');
    $html  = '<div class="notice notice-success"><p><strong>Draft created:</strong> '
           . esc_html($data['title']) . ' &mdash; <a href="' . esc_url($edit_url) . '">open and review it</a>. '
           . 'Remember to set the price and stock before publishing.</p>';
    $html .= '<p>Category: ' . esc_html($data['category']) . ' | Tags: ' . esc_html(implode(', ', (array) $data['tags']))
           . '<br>SEO title: ' . esc_html($seo_title) . '<br>Meta description: ' . esc_html($meta_desc) . '</p>';
    if ($data['status'] !== 'approved') {
        $why = empty($data['issues']) ? 'the AI image analysis was not available, so the text is a basic template' : implode('; ', (array) $data['issues']);
        $html .= '<p><strong>Please review carefully:</strong> ' . esc_html($why) . '</p>';
    }
    $html .= '<details><summary>What the agent did (' . intval($data['attempts']) . ' attempt(s))</summary><ol>';
    foreach ((array) $data['steps'] as $step) {
        $html .= '<li>' . esc_html($step) . '</li>';
    }
    $html .= '</ol></details></div>';
    return $html;
}

add_action('admin_menu', function () {
    add_submenu_page('woocommerce', 'AI Product Onboarding', 'AI Product Onboarding', 'edit_products', 'ds-agents-onboarding', 'ds_onboarding_page');
});

function ds_onboarding_page() {
    if (!current_user_can('edit_products')) {
        return;
    }
    $notice = '';
    if (isset($_POST['ds_onboard_submit']) && check_admin_referer('ds_onboard')) {
        $notice = ds_onboarding_handle();
    }

    echo '<div class="wrap"><h1>AI Product Onboarding</h1>' . $notice;
    echo '<p>Upload <strong>one product photo</strong> and type the product name. The AI writes the description, SEO text, tags and category, and creates a <strong>Draft</strong> product for you to review.</p>';
    echo '<form method="post" enctype="multipart/form-data">';
    wp_nonce_field('ds_onboard');
    echo '<table class="form-table">';
    echo '<tr><th><label for="ds_name">Product name</label></th><td><input type="text" id="ds_name" name="product_name" class="regular-text" required maxlength="150"></td></tr>';
    echo '<tr><th><label for="ds_image">Product photo</label></th><td><input type="file" id="ds_image" name="image" accept="image/jpeg,image/png,image/webp" required><p class="description">JPG, PNG or WebP, up to 10 MB.</p></td></tr>';
    echo '</table>';
    submit_button('Create draft with AI', 'primary', 'ds_onboard_submit');
    echo '</form>';
    echo '<p class="description">This can take up to a minute: the AI service may need to wake up, and the AI may rewrite the text a few times until it meets the rules.</p>';
    echo '</div>';
}
