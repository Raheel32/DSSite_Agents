/**
 * Code Snippets (type: PHP, run everywhere).
 * Agent 4 - Fraud check. Every order is sent to the agent when it reaches Processing or On hold.
 * Works with the classic AND the block checkout. Adds an order note with the verdict, and puts
 * Flagged orders On hold. If the agent is unreachable the order is NEVER blocked.
 * Needs the config snippet (DS_AGENTS_SITE_KEY).
 */
function ds_fraud_check_order($order) {
    if (!($order instanceof WC_Order)) {
        return;
    }
    if ($order->get_meta('_ds_fraud_checked')) {
        return;   // never check the same order twice
    }
    $order->update_meta_data('_ds_fraud_checked', '1');
    $order->save();

    $site_key = defined('DS_AGENTS_SITE_KEY') ? DS_AGENTS_SITE_KEY : '';   // set in the config snippet
    $headers  = ['Content-Type' => 'application/json'];
    if ($site_key !== '') {
        $headers['X-Site-Key'] = $site_key;
    }

    $payload = [
        'order_ref'        => (string) $order->get_order_number(),
        'customer_email'   => $order->get_billing_email(),
        'amount'           => (float) $order->get_total(),
        'payment_method'   => $order->get_payment_method() === 'cod' ? 'cod' : 'bank_transfer',
        'ip_address'       => $order->get_customer_ip_address(),
        'shipping_country' => $order->get_shipping_country() ? $order->get_shipping_country() : $order->get_billing_country(),
    ];

    $res = wp_remote_post('https://ai-agents-service-tdhq.onrender.com/fraud/check', [
        'timeout' => 60,   // the free Render service can take about a minute to wake up
        'headers' => $headers,
        'body'    => wp_json_encode($payload),
    ]);

    if (is_wp_error($res)) {
        $order->add_order_note('Fraud agent unreachable: ' . $res->get_error_message());
        return;
    }
    $code = wp_remote_retrieve_response_code($res);
    $data = json_decode(wp_remote_retrieve_body($res), true);
    if ($code !== 200 || empty($data['verdict'])) {
        $order->add_order_note('Fraud agent error (HTTP ' . intval($code) . '): ' . substr(wp_remote_retrieve_body($res), 0, 200));
        return;
    }

    $note = 'Fraud agent: ' . $data['verdict'] . ' (score ' . intval($data['fraud_score']) . ')';
    if (!empty($data['reasons'])) {
        $note .= ' - ' . implode('; ', (array) $data['reasons']);
    }
    $order->add_order_note($note);

    if ($data['verdict'] === 'Flagged') {
        $order->update_status('on-hold', 'Flagged by fraud agent for review.');
    }
}

// Runs whenever an order moves to Processing or On hold (works for every checkout type)
add_action('woocommerce_order_status_changed', function ($order_id, $from, $to, $order) {
    if (!in_array($to, ['processing', 'on-hold'], true)) {
        return;
    }
    ds_fraud_check_order($order ? $order : wc_get_order($order_id));
}, 10, 4);
