/**
 * Code Snippets (type: PHP, run everywhere).
 * Adds the shortcode [ds_refund_form] - put it on a page (e.g. "Request a Refund").
 * The order facts are read from WooCommerce on the SERVER, so customers cannot fake them.
 */
add_shortcode('ds_refund_form', function () {
    $api      = 'https://ai-agents-service-tdhq.onrender.com/refund/request';
    $site_key = '';   // paste the SAME value you set as SITE_API_KEY on Render ('' = no key)
    $out      = '';

    if (isset($_POST['ds_refund_submit'], $_POST['_wpnonce']) && wp_verify_nonce($_POST['_wpnonce'], 'ds_refund')) {
        $order_no = absint($_POST['order_no'] ?? 0);
        $email    = sanitize_email(wp_unslash($_POST['email'] ?? ''));
        $message  = sanitize_textarea_field(wp_unslash($_POST['message'] ?? ''));
        $order    = $order_no ? wc_get_order($order_no) : false;

        if (!$order || strtolower($order->get_billing_email()) !== strtolower($email) || strlen($message) < 3) {
            $out .= '<p><strong>We could not find an order matching those details. Please check and try again.</strong></p>';
        } else {
            $done    = $order->get_date_completed();
            $created = $order->get_date_created();
            $payload = [
                'order_ref'      => (string) $order->get_order_number(),
                'customer_email' => $email,
                'message'        => $message,
                'order'          => [
                    'amount'         => (float) $order->get_total(),
                    'payment_method' => $order->get_payment_method() === 'cod' ? 'cod' : 'bank_transfer',
                    'status'         => $order->get_status(),
                    'order_date'     => $created ? $created->format('c') : null,
                    'delivered_at'   => $done ? $done->format('c') : null,
                ],
            ];
            $headers = ['Content-Type' => 'application/json'];
            if ($site_key !== '') { $headers['X-Site-Key'] = $site_key; }

            $res = wp_remote_post($api, ['timeout' => 60, 'headers' => $headers, 'body' => wp_json_encode($payload)]);

            if (is_wp_error($res)) {
                $out .= '<p><strong>Sorry, our refund service is busy. Please try again in a minute.</strong></p>';
            } else {
                $code = wp_remote_retrieve_response_code($res);
                $data = json_decode(wp_remote_retrieve_body($res), true);
                if ($code === 409) {
                    $out .= '<p><strong>A request for this order already exists. Our team is on it.</strong></p>';
                } elseif ($code !== 200 || empty($data['status'])) {
                    $out .= '<p><strong>Sorry, something went wrong. Please contact us.</strong></p>';
                } else {
                    $ref = ' (request #' . intval($data['request_id']) . ')';
                    if ($data['status'] === 'auto_approved') {
                        $out .= '<p><strong>Approved' . $ref . '.</strong> ' . esc_html($data['reason']) . '</p>';
                    } elseif ($data['status'] === 'auto_rejected') {
                        $out .= '<p><strong>Not eligible' . $ref . '.</strong> ' . esc_html($data['reason']) . '</p>';
                    } else {
                        $out .= '<p><strong>Received' . $ref . '.</strong> Our team will review your request and get back to you.</p>';
                    }
                }
            }
        }
    }

    ob_start(); ?>
    <form method="post" class="ds-refund-form">
        <?php wp_nonce_field('ds_refund'); ?>
        <p><label>Order number<br><input type="number" name="order_no" required></label></p>
        <p><label>Email used for the order<br><input type="email" name="email" required></label></p>
        <p><label>What went wrong?<br><textarea name="message" rows="4" required></textarea></label></p>
        <p><button type="submit" name="ds_refund_submit" value="1">Request refund / cancellation</button></p>
    </form>
    <?php
    return $out . ob_get_clean();
});
