/**
 * Code Snippets (type: PHP, run in admin only or everywhere).
 * Adds  WooCommerce > "AI Agents"  inside your WordPress admin:
 *   - refund / cancel requests waiting for you (Approve / Reject buttons)
 *   - recent refund requests with the agent's reasoning
 *   - orders flagged by the fraud agent
 * Your ADMIN_API_KEY stays on the server (inside this snippet), never in the browser.
 */
function ds_admin_api($path, $method = 'GET', $body = null) {
    $admin_key = defined('DS_AGENTS_ADMIN_KEY') ? DS_AGENTS_ADMIN_KEY : '';   // set in the config snippet
    $args = [
        'method'  => $method,
        'timeout' => 60,   // the free Render service can take ~1 minute to wake up
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

function ds_dash_table($headers, $rows) {
    if (empty($rows)) {
        return '<p>Nothing here.</p>';
    }
    $html = '<table class="widefat striped"><thead><tr>';
    foreach ($headers as $title) {
        $html .= '<th>' . esc_html($title) . '</th>';
    }
    $html .= '</tr></thead><tbody>';
    foreach ($rows as $row) {
        $html .= '<tr>';
        foreach ($row as $cell) {
            $html .= '<td>' . $cell . '</td>';   // every cell is already escaped by the caller
        }
        $html .= '</tr>';
    }
    return $html . '</tbody></table>';
}

function ds_dash_order_link($order_ref) {
    $label = esc_html($order_ref);
    $order = ctype_digit((string) $order_ref) ? wc_get_order((int) $order_ref) : false;
    if ($order) {
        return '<a href="' . esc_url($order->get_edit_order_url()) . '">#' . $label . '</a>';
    }
    return '#' . $label;
}

function ds_dash_status($status) {
    $colors = [
        'pending_approval' => '#ffe08a',
        'approved'         => '#c8f2d0',
        'auto_approved'    => '#c8f2d0',
        'rejected'         => '#f7c5c5',
        'auto_rejected'    => '#f7c5c5',
        'Flagged'          => '#f7c5c5',
    ];
    $bg = isset($colors[$status]) ? $colors[$status] : '#e5e5e5';
    return '<span style="padding:2px 8px;border-radius:10px;background:' . esc_attr($bg) . '">' . esc_html($status) . '</span>';
}

function ds_dash_when($iso) {
    if (empty($iso)) {
        return '';
    }
    return esc_html(get_date_from_gmt(str_replace('T', ' ', substr($iso, 0, 19)), 'Y-m-d H:i'));
}

function ds_dash_error($code, $data, $raw) {
    if ($code === 0) {
        return 'Could not reach the agent service: ' . $raw;
    }
    if ($code === 401) {
        return 'The agent service refused the key. Check the ADMIN_API_KEY value in this snippet.';
    }
    if (is_array($data) && isset($data['detail']) && is_string($data['detail'])) {
        return $data['detail'];
    }
    return 'Unexpected answer (HTTP ' . intval($code) . ').';
}

add_action('admin_menu', function () {
    add_submenu_page('woocommerce', 'AI Agents', 'AI Agents', 'manage_woocommerce', 'ds-agents-dashboard', 'ds_agents_dashboard_page');
});

function ds_agents_dashboard_page() {
    if (!current_user_can('manage_woocommerce')) {
        return;
    }

    $notice = '';
    if (isset($_POST['ds_decision']) && check_admin_referer('ds_decide_refund')) {
        $decision = ($_POST['ds_decision'] === 'approve') ? 'approve' : 'reject';
        list($code, $data, $raw) = ds_admin_api('/approve-refund', 'POST', [
            'request_id' => absint($_POST['request_id'] ?? 0),
            'decision'   => $decision,
            'note'       => sanitize_text_field(wp_unslash($_POST['note'] ?? '')),
        ]);
        if ($code === 200 && is_array($data)) {
            $notice = '<div class="notice notice-success"><p>Request #' . intval($data['request_id']) . ' is now <strong>' . esc_html($data['status']) . '</strong>.</p></div>';
        } else {
            $notice = '<div class="notice notice-error"><p>' . esc_html(ds_dash_error($code, $data, $raw)) . '</p></div>';
        }
    }

    list($c1, $pending, $r1) = ds_admin_api('/refund/requests?status=pending_approval');
    list($c2, $recent, $r2)  = ds_admin_api('/refund/requests?limit=20');
    list($c3, $flagged, $r3) = ds_admin_api('/fraud/flagged');

    echo '<div class="wrap"><h1>AI Agents</h1>' . $notice;

    // ---- Pending refund approvals
    echo '<h2>Refund and cancel requests waiting for you</h2>';
    if ($c1 !== 200 || !is_array($pending)) {
        echo '<div class="notice notice-error"><p>' . esc_html(ds_dash_error($c1, $pending, $r1)) . '</p></div>';
    } else {
        $rows = [];
        foreach ($pending as $r) {
            $form  = '<form method="post" style="display:flex;gap:6px;flex-wrap:wrap;align-items:center">';
            $form .= wp_nonce_field('ds_decide_refund', '_wpnonce', true, false);
            $form .= '<input type="hidden" name="request_id" value="' . intval($r['id']) . '">';
            $form .= '<input type="text" name="note" placeholder="Optional note" maxlength="200">';
            $form .= '<button class="button button-primary" name="ds_decision" value="approve">Approve</button>';
            $form .= '<button class="button" name="ds_decision" value="reject">Reject</button>';
            $form .= '</form>';
            $rows[] = [
                intval($r['id']),
                ds_dash_order_link($r['order_ref']),
                esc_html($r['customer_email']),
                esc_html(number_format((float) $r['refund_amount'])),
                esc_html($r['message']),
                esc_html($r['reason']),
                ds_dash_when($r['created_at']),
                $form,
            ];
        }
        echo ds_dash_table(['ID', 'Order', 'Customer', 'Amount (Rs)', 'Customer message', 'Why it needs you', 'When', 'Decision'], $rows);
    }

    // ---- Recent requests
    echo '<h2 style="margin-top:30px">Recent refund requests</h2>';
    if ($c2 === 200 && is_array($recent)) {
        $rows = [];
        foreach ($recent as $r) {
            $rows[] = [
                intval($r['id']),
                ds_dash_order_link($r['order_ref']),
                esc_html($r['intent']),
                ds_dash_status($r['status']),
                esc_html($r['reason']),
                ds_dash_when($r['created_at']),
            ];
        }
        echo ds_dash_table(['ID', 'Order', 'Intent', 'Status', 'Reason', 'When'], $rows);
    }

    // ---- Fraud flagged
    echo '<h2 style="margin-top:30px">Orders flagged by the fraud agent</h2>';
    if ($c3 === 200 && is_array($flagged)) {
        $rows = [];
        foreach ($flagged as $f) {
            $rows[] = [
                ds_dash_order_link($f['order_ref']),
                intval($f['fraud_score']),
                ds_dash_status($f['verdict']),
                esc_html(implode('; ', (array) $f['reasons'])),
            ];
        }
        echo ds_dash_table(['Order', 'Score', 'Verdict', 'Reasons'], $rows);
    }

    echo '</div>';
}
