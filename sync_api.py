# -*- coding: utf-8 -*-
import json
import uuid
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify

sync_bp = Blueprint('sync_bp', __name__)

def register_sync_routes(app, get_db, normalize_phone, calculate_customer_summary, publish_sync_event):

    @app.route('/api/v1/sync/eeyes-state', methods=['GET', 'POST'])
    def api_sync_eeyes_state():
        """
        Unified 2-way sync API between Eeyes Pro and Eeyes Repo.
        GET: Returns all customers, their wallet balances, linked bills, and batch rewards with codes.
        POST: Ingests parties and bills from Eeyes Pro, reconciles wallet and batches, and returns full state.
        """
        conn = get_db()
        cursor = conn.cursor()
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        if request.method == 'POST':
            data = request.json or {}
            parties = data.get('parties', [])
            invoices = data.get('invoices', [])

            for p in parties:
                phone = normalize_phone(p.get('phone', ''))
                if len(phone) < 10:
                    continue
                name = str(p.get('name', '')).strip()
                if not name:
                    continue

                cursor.execute('SELECT * FROM customers WHERE phone = ?', (phone,))
                if cursor.fetchone():
                    cursor.execute('''
                    UPDATE customers SET name = ?, address = ?, city = ?, pincode = ? WHERE phone = ?
                    ''', (name, p.get('address', ''), p.get('city', ''), p.get('pincode', ''), phone))
                else:
                    cursor.execute('''
                    INSERT INTO customers (phone, name, email, avatar_color, vip_tier, address, city, pincode, created_at)
                    VALUES (?, ?, ?, '#2563EB', 'Silver', ?, ?, ?, ?)
                    ''', (phone, name, p.get('email', f"{phone}@rewards.espro"), p.get('address', ''), p.get('city', ''), p.get('pincode', ''), now_str))

                for b in p.get('reward_batches', []):
                    b_id = b.get('batch_id')
                    if not b_id:
                        continue
                    inv_no = b.get('invoice_no', 'OPENING')
                    earned = float(b.get('earned_amount', 0))
                    remaining = float(b.get('balance_amount', earned))
                    earned_dt = b.get('earned_date', now_str.split(' ')[0])
                    mat_dt = b.get('maturity_date', earned_dt)
                    exp_dt = b.get('expiry_date', '2026-11-29 23:59:59')
                    red_code = b.get('redemption_code') or f"OP-{b_id[-4:]}-K82F"
                    req_bill = float(b.get('required_bill_amount', round(earned * 10.0, 2)))
                    st = b.get('status', 'ACTIVE')

                    cursor.execute('''
                    INSERT OR REPLACE INTO reward_batches (
                        id, customer_phone, firm_id, invoice_no, bill_amount,
                        points_earned, points_remaining, earned_date, expiry_date,
                        required_bill_to_redeem, status, created_at, redemption_code, maturity_date
                    ) VALUES (?, ?, 'firm-es-pro', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (b_id, phone, inv_no, b.get('bill_amount', req_bill), earned, remaining, earned_dt, exp_dt, req_bill, st, now_str, red_code, mat_dt))

            for inv in invoices:
                inv_no = inv.get('invoiceNo')
                phone = normalize_phone(inv.get('partyPhone', inv.get('customer_phone', '')))
                if not inv_no or len(phone) < 10:
                    continue
                amt = float(inv.get('grandTotal', inv.get('amount', 0)))
                pts = float(inv.get('earnedRewardPoints', inv.get('rewardPoints', 0)))
                cursor.execute('''
                INSERT OR REPLACE INTO firm_invoices (
                    id, customer_phone, firm_id, invoice_type, invoice_no, amount,
                    items_count, payment_mode, points_affected, notes, invoice_date, created_at
                ) VALUES (?, ?, 'firm-es-pro', 'PURCHASE', ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (inv_no, phone, inv_no, amt, len(inv.get('items', [])) or 1, inv.get('paymentMode', 'Cash').upper(), pts, inv.get('notes', 'Retail Sale'), inv.get('date', now_str.split(' ')[0]), now_str))

            conn.commit()

        cursor.execute('SELECT phone, name, email, avatar_color, vip_tier, address, city, pincode, created_at FROM customers')
        customers = [dict(r) for r in cursor.fetchall()]

        cursor.execute('''
        SELECT id, customer_phone, firm_id, invoice_no, bill_amount, points_earned, points_remaining,
               earned_date, expiry_date, required_bill_to_redeem, status, redemption_code, maturity_date
        FROM reward_batches
        ORDER BY created_at DESC
        ''')
        batches = [dict(r) for r in cursor.fetchall()]

        cursor.execute('''
        SELECT id, customer_phone, firm_id, invoice_type, invoice_no, amount, items_count, payment_mode,
               points_affected, notes, invoice_date, created_at
        FROM firm_invoices
        ORDER BY invoice_date DESC
        ''')
        invoices_list = [dict(r) for r in cursor.fetchall()]
        conn.close()

        batches_by_phone = {}
        for b in batches:
            ph = b['customer_phone']
            if ph not in batches_by_phone:
                batches_by_phone[ph] = []
            batches_by_phone[ph].append(b)

        for c in customers:
            ph = c['phone']
            c['batches'] = batches_by_phone.get(ph, [])
            c['total_wallet_balance'] = sum(float(b['points_remaining']) for b in c['batches'] if b.get('status') == 'ACTIVE')

        return jsonify({
            'success': True,
            'timestamp': datetime.now().isoformat(),
            'customers': customers,
            'batches': batches,
            'invoices': invoices_list
        })

    @app.route('/api/v1/sync/push-bill', methods=['POST'])
    def api_sync_push_bill():
        """
        Real-time API called whenever an invoice/bill is generated in Eeyes Pro.
        Links bill to customer, creates batch-wise reward with unique verification code,
        and updates customer's centralized wallet.
        """
        data = request.json or {}
        invoice_no = str(data.get('invoiceNo') or data.get('invoice_no') or '').strip()
        phone = normalize_phone(data.get('partyPhone') or data.get('customer_phone') or '')
        party_name = str(data.get('partyName') or data.get('customer_name') or 'Customer').strip()
        grand_total = float(data.get('grandTotal') or data.get('amount') or 0.0)
        reward_points = float(data.get('rewardPoints') or data.get('earnedRewardPoints') or 0.0)
        payment_mode = str(data.get('paymentMode') or 'Cash').upper()
        date_str = str(data.get('date') or datetime.now().strftime('%Y-%m-%d')).strip()
        items = data.get('items', [])

        if not invoice_no:
            return jsonify({'success': False, 'message': 'Invoice Number is required'}), 400
        if len(phone) < 10:
            return jsonify({'success': False, 'message': 'Valid 10-digit customer phone is required'}), 400

        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM customers WHERE phone = ?', (phone,))
        cust = cursor.fetchone()
        if not cust:
            cursor.execute('''
            INSERT INTO customers (phone, name, email, avatar_color, vip_tier, created_at)
            VALUES (?, ?, ?, '#2563EB', 'Silver', ?)
            ''', (phone, party_name, f"{phone}@rewards.espro", now_str))

        cursor.execute('''
        INSERT OR REPLACE INTO firm_invoices (
            id, customer_phone, firm_id, invoice_type, invoice_no, amount,
            items_count, payment_mode, points_affected, notes, invoice_date, created_at
        ) VALUES (?, ?, 'firm-es-pro', 'PURCHASE', ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (invoice_no, phone, invoice_no, grand_total, len(items) or 1, payment_mode, reward_points, f"EEYES Pro Bill #{invoice_no}", date_str, now_str))

        batch_record = None
        if reward_points > 0:
            cursor.execute('SELECT * FROM reward_batches WHERE invoice_no = ?', (invoice_no,))
            existing_batch = cursor.fetchone()
            if existing_batch:
                batch_record = dict(existing_batch)
            else:
                b_suffix = invoice_no.replace('INV-', '').replace('-', '')[-4:]
                b_id = f"BAT_{datetime.now().strftime('%Y%m%d')}_{b_suffix}"
                red_code = f"OP-{b_suffix}-{uuid.uuid4().hex[:4].upper()}"
                mat_date = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
                exp_date = (datetime.now() + timedelta(days=14)).strftime('%Y-%m-%d 23:59:59')
                req_bill = round(reward_points * 10.0, 2)

                cursor.execute('''
                INSERT INTO reward_batches (
                    id, customer_phone, firm_id, invoice_no, bill_amount,
                    points_earned, points_remaining, earned_date, expiry_date,
                    required_bill_to_redeem, status, created_at, redemption_code, maturity_date
                ) VALUES (?, ?, 'firm-es-pro', ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?, ?)
                ''', (b_id, phone, invoice_no, grand_total, reward_points, reward_points, date_str, exp_date, req_bill, now_str, red_code, mat_date))

                tx_id = f"TX-REW-{b_id}"
                cursor.execute('''
                INSERT INTO transactions (id, customer_phone, firm_id, type, points, amount_equivalent, bill_no, bill_amount, description, batch_ids, created_at)
                VALUES (?, ?, 'firm-es-pro', 'EARN', ?, ?, ?, ?, ?, ?, ?)
                ''', (tx_id, phone, reward_points, reward_points, invoice_no, grand_total, f"Reward from Bill #{invoice_no} (Batch {b_id})", b_id, now_str))

                cursor.execute('SELECT * FROM reward_batches WHERE id = ?', (b_id,))
                batch_record = dict(cursor.fetchone())

        conn.commit()
        conn.close()

        summary = calculate_customer_summary(phone)

        try:
            publish_sync_event({
                'type': 'BILL_SYNC',
                'invoice_no': invoice_no,
                'customer_phone': phone,
                'points_earned': reward_points,
                'batch': batch_record,
                'wallet': summary
            })
        except Exception:
            pass

        return jsonify({
            'success': True,
            'message': f"Bill {invoice_no} synced and batch reward linked successfully!",
            'invoice_no': invoice_no,
            'customer_phone': phone,
            'batch': batch_record,
            'updated_wallet': summary
        })

    @app.route('/api/v1/sync/customer-wallet/<phone>', methods=['GET'])
    def api_sync_get_customer_wallet(phone):
        """
        Returns customer's full wallet, linked bills, and batch-wise rewards with redemption codes.
        """
        phone = normalize_phone(phone)
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM customers WHERE phone = ?', (phone,))
        cust = cursor.fetchone()
        if not cust:
            conn.close()
            return jsonify({'success': False, 'message': 'Customer not found'}), 404

        cursor.execute('''
        SELECT id, invoice_no, bill_amount, points_earned, points_remaining,
               earned_date, expiry_date, required_bill_to_redeem, status, redemption_code, maturity_date
        FROM reward_batches
        WHERE customer_phone = ?
        ORDER BY created_at DESC
        ''', (phone,))
        batches = [dict(r) for r in cursor.fetchall()]

        cursor.execute('''
        SELECT invoice_no, amount, items_count, payment_mode, points_affected, invoice_date, created_at
        FROM firm_invoices
        WHERE customer_phone = ?
        ORDER BY invoice_date DESC
        ''', (phone,))
        invoices = [dict(r) for r in cursor.fetchall()]
        conn.close()

        summary = calculate_customer_summary(phone)

        return jsonify({
            'success': True,
            'customer': dict(cust),
            'wallet_summary': summary,
            'active_batches': [b for b in batches if b.get('status') == 'ACTIVE'],
            'all_batches': batches,
            'linked_bills': invoices
        })
