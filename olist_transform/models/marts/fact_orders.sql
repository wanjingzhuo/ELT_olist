WITH orders AS ( -- grain: one row per order item
    SELECT
        order_id,
        customer_id,
        order_status,
        order_purchase_timestamp,
        order_approved_at,
        order_delivered_carrier_date,
        order_delivered_customer_date,
        order_estimated_delivery_date
    FROM {{ ref('stg_orders') }}
),

order_items AS (
    SELECT
        order_id,
        order_item_id,
        product_id,
        seller_id,
        shipping_limit_date,
        price,
        freight_value
    FROM {{ ref('stg_order_items') }}
),

payments AS (
    SELECT
        order_id,
        SUM(payment_value) AS total_payment_value,
        MAX(payment_installments) AS max_installments
    FROM {{ ref('stg_order_payments') }}
    GROUP BY order_id
    -- payment_type is excluded because orders can have multiple types  
),

final AS (
    SELECT
        -- Keys
        {{ dbt_utils.generate_surrogate_key(['oi.order_id', 'oi.order_item_id']) }} AS order_item_sk,
        oi.order_id,
        oi.order_item_id,
        o.customer_id,
        oi.product_id,
        oi.seller_id,

        -- Order info
        o.order_status,
        o.order_purchase_timestamp,
        o.order_approved_at,
        o.order_delivered_carrier_date,
        o.order_delivered_customer_date,
        o.order_estimated_delivery_date,
        oi.shipping_limit_date,

        -- Financials
        oi.price,
        oi.freight_value,
        p.total_payment_value,
        p.max_installments,

        -- Derived delivery metrics
        DATE_DIFF(o.order_delivered_customer_date, o.order_purchase_timestamp, DAY) AS delivery_days,
        DATE_DIFF(o.order_estimated_delivery_date, o.order_purchase_timestamp, DAY) AS estimated_delivery_days,
        CASE 
            WHEN o.order_delivered_customer_date > o.order_estimated_delivery_date THEN TRUE
            ELSE FALSE
        END AS is_late

    FROM order_items AS oi 
    LEFT JOIN orders AS o ON oi.order_id = o.order_id
    LEFT JOIN payments AS p ON oi.order_id = p.order_id 
)

SELECT * FROM final

-- Questions fact_orders can answer:
-- Average order value
-- On-time vs late deliveries by state/seller
-- Freight cost vs product weight
-- Payment installment patterns