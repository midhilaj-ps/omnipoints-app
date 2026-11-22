import os
import json
import sqlite3
import random
import time
import uuid
import asyncio
import threading
import websockets
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template, send_from_directory, Response
from flask_cors import CORS

app = Flask(__name__, static_folder='static', template_folder='templates')
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
CORS(app)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'omnipoints.db')

# Ensure static & templates directory exists
os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'css'), exist_ok=True)
os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'js'), exist_ok=True)
os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'icons'), exist_ok=True)
os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates'), exist_ok=True)

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA busy_timeout=30000;')
    return conn

def init_db():
    conn = get_db()
    try:
        conn.execute('PRAGMA journal_mode=WAL;')
        conn.execute('PRAGMA synchronous=NORMAL;')
    except Exception:
        pass
    cursor = conn.cursor()

    # Customers table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS customers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        phone TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        email TEXT,
        avatar_color TEXT DEFAULT '#4F46E5',
        vip_tier TEXT DEFAULT 'Silver',
        created_at TEXT NOT NULL
    )
    ''')

    # Participating Partner Firms / Business Categories
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS firms (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        category TEXT NOT NULL,
        category_icon TEXT NOT NULL,
        tagline TEXT,
        address TEXT,
        badge TEXT,
        theme_color TEXT,
        logo_url TEXT,
        banner_url TEXT,
        min_purchase_multiplier REAL DEFAULT 1.0,
        min_bill_amount REAL DEFAULT 0,
        max_redemption_pct REAL DEFAULT 100.0,
        max_points_per_txn REAL DEFAULT 999999.0,
        validity_days INTEGER DEFAULT 7,
        next_day_redemption_only INTEGER DEFAULT 0,
        rule_summary TEXT,
        is_es_pro INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    )
    ''')

    # Reward Batches table (Batch-wise rewards with individual expiry and rules)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS reward_batches (
        id TEXT PRIMARY KEY,
        customer_phone TEXT NOT NULL,
        firm_id TEXT NOT NULL,
        invoice_no TEXT NOT NULL,
        bill_amount REAL NOT NULL,
        points_earned REAL NOT NULL,
        points_remaining REAL NOT NULL,
        earned_date TEXT NOT NULL,
        expiry_date TEXT NOT NULL,
        required_bill_to_redeem REAL NOT NULL,
        status TEXT DEFAULT 'ACTIVE', -- ACTIVE, MATURED, EXPIRED, REDEEMED
        created_at TEXT NOT NULL,
        FOREIGN KEY (customer_phone) REFERENCES customers (phone),
        FOREIGN KEY (firm_id) REFERENCES firms (id)
    )
    ''')

    # Transactions Ledger (Earned, Redeemed, Expired)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS transactions (
        id TEXT PRIMARY KEY,
        customer_phone TEXT NOT NULL,
        firm_id TEXT NOT NULL,
        type TEXT NOT NULL, -- EARN, REDEEM, EXPIRE, BONUS
        points REAL NOT NULL,
        amount_equivalent REAL NOT NULL,
        bill_no TEXT,
        bill_amount REAL,
        description TEXT,
        batch_ids TEXT,
        created_at TEXT NOT NULL
    )
    ''')

    # Firm Promotions, Banner Ads & Exclusive Offers
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS firm_offers (
        id TEXT PRIMARY KEY,
        firm_id TEXT NOT NULL,
        title TEXT NOT NULL,
        tag TEXT NOT NULL,
        description TEXT NOT NULL,
        coupon_code TEXT,
        valid_till TEXT NOT NULL,
        discount_text TEXT,
        ad_banner TEXT,
        highlight INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    )
    ''')

    # Scratch Cards / Gamified Rewards
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS scratch_cards (
        id TEXT PRIMARY KEY,
        customer_phone TEXT NOT NULL,
        title TEXT NOT NULL,
        points_reward REAL NOT NULL,
        is_scratched INTEGER DEFAULT 0,
        scratched_at TEXT,
        created_at TEXT NOT NULL
    )
    ''')

    # Active Counter Redemption Tokens (Temporary OTP / QR tokens for cashiers)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS redemption_tokens (
        token TEXT PRIMARY KEY,
        otp TEXT NOT NULL,
        customer_phone TEXT NOT NULL,
        firm_id TEXT NOT NULL,
        points_to_redeem REAL NOT NULL,
        selected_batches TEXT,
        expires_at TEXT NOT NULL,
        status TEXT DEFAULT 'PENDING' -- PENDING, COMPLETED, CANCELLED, EXPIRED
    )
    ''')

    # Multi-Firm Customer Profiles (Tracks varied registered names across different partner firms)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS firm_customer_profiles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_phone TEXT NOT NULL,
        firm_id TEXT NOT NULL,
        registered_name TEXT NOT NULL,
        account_no TEXT,
        created_at TEXT NOT NULL,
        UNIQUE(customer_phone, firm_id)
    )
    ''')

    # Invoices & Goods Return / Surrender Slips Ledger
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS firm_invoices (
        id TEXT PRIMARY KEY,
        customer_phone TEXT NOT NULL,
        firm_id TEXT NOT NULL,
        invoice_type TEXT NOT NULL DEFAULT 'PURCHASE', -- 'PURCHASE' or 'RETURN'
        invoice_no TEXT NOT NULL,
        amount REAL NOT NULL,
        items_count INTEGER DEFAULT 1,
        payment_mode TEXT DEFAULT 'CASH',
        points_affected REAL DEFAULT 0.0,
        notes TEXT,
        invoice_date TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (firm_id) REFERENCES firms (id)
    )
    ''')

    # OTP Verifications for Phone Login
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS otp_verifications (
        phone TEXT PRIMARY KEY,
        otp TEXT NOT NULL,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL
    )
    ''')

    # Pending Live Redemption Claims (initiated by customer clicking "Redeem Now")
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS pending_redemption_claims (
        id TEXT PRIMARY KEY,
        customer_phone TEXT NOT NULL,
        customer_name TEXT,
        firm_id TEXT NOT NULL,
        points REAL NOT NULL,
        batch_id TEXT,
        batch_invoice_no TEXT,
        required_bill REAL DEFAULT 0,
        status TEXT DEFAULT 'PENDING',
        created_at TEXT NOT NULL
    )
    ''')

    # Merchant-initiated live redemption approval requests (EEYES Pro cashier sends request to customer)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS merchant_redemption_requests (
        id TEXT PRIMARY KEY,
        phone TEXT NOT NULL,
        customer_name TEXT,
        firm_id TEXT NOT NULL,
        firm_name TEXT NOT NULL,
        invoice_no TEXT,
        points REAL NOT NULL,
        bill_amount REAL DEFAULT 0,
        status TEXT DEFAULT 'PENDING',
        created_at TEXT NOT NULL,
        updated_at TEXT
    )
    ''')

    conn.commit()

    # Seed Initial Data if empty
    cursor.execute('SELECT COUNT(*) FROM customers')
    if cursor.fetchone()[0] == 0:
        seed_data(cursor)
        conn.commit()

    # Seed multi-firm profiles if empty
    cursor.execute('SELECT COUNT(*) FROM firm_customer_profiles')
    if cursor.fetchone()[0] == 0:
        seed_firm_profiles(cursor)
        conn.commit()

    conn.close()

    # Automatically synchronize all EEYES PRO Desktop records into OmniPoints
    try:
        sync_from_eeyes_pro()
    except Exception as e:
        print(f"[EeyesSync] Startup sync note: {e}")

def seed_data(cursor):
    now = datetime.now()
    now_str = now.strftime('%Y-%m-%d %H:%M:%S')

    # 1. Seed Firms (including ES PRO Supermarket, Petrol Pump, Cafe, Electronics, Fashion, Wellness)
    firms = [
        (
            'firm-es-pro',
            'ES Supermarket & Department Store',
            'Supermarket & Groceries',
            'shopping-cart',
            'Official ES PRO ERP Network Store - Groceries, Essentials & Produce',
            'ES Commercial Complex, Main Road, Calicut',
            'ES PRO FLAGSHIP',
            '#059669', # Emerald
            'es_logo.png',
            'https://images.unsplash.com/photo-1578916171728-46686eac8d58?w=800&auto=format&fit=crop&q=80',
            10.0, # 10x Purchase Rule: bill must be >= 10x reward points to unlock
            50.0,
            100.0,
            5000.0,
            7,    # 7-day validity
            1,    # Next-day redemption policy active
            '10x Multiplier Rule: Bill must be >= 10x points. 7-day validity. Matures next day after purchase.',
            1,
            now_str
        ),
        (
            'firm-petro',
            'Highway Petroleum & CNG Hub',
            'Fuel & Energy',
            'fuel',
            'High Performance Fuels, Speed Diesel, CNG & Auto Lubricants',
            'National Highway 66 Bypass, Wayanad Junction',
            '24/7 EXPRESS FUEL',
            '#EA580C', # Orange
            'petro_logo.png',
            'https://images.unsplash.com/photo-1545459720-aac8509eb02c?w=800&auto=format&fit=crop&q=80',
            1.0,
            500.0, # Min fuel bill: ₹500
            25.0,  # Max 25% of fuel bill
            150.0, # Max ₹150 per fuel fill
            14,    # 14 days validity
            0,     # Instant redemption allowed
            'Redeem up to ₹150 or 25% of bill on minimum ₹500 fuel purchase. Instant pump deduction.',
            0,
            now_str
        ),
        (
            'firm-cafe',
            'Bean & Bloom Artisan Café',
            'Café & Bakery',
            'coffee',
            'Single Origin Brews, French Patisserie & Continental Bistro',
            'Boutique Street, 2nd Cross, City Center',
            'PREMIUM LOUNGE',
            '#854D0E', # Amber
            'cafe_logo.png',
            'https://images.unsplash.com/photo-1501339847302-ac426a4a7cbb?w=800&auto=format&fit=crop&q=80',
            1.0,
            250.0, # Min bill ₹250
            20.0,  # Max 20% of bill
            300.0,
            10,    # 10 days validity
            0,     # Instant redemption allowed
            'Redeem up to 20% on any dining or takeaway bill above ₹250. No waiting period.',
            0,
            now_str
        ),
        (
            'firm-nexus',
            'Nexus Tech & Smartphone Lounge',
            'Electronics & Gadgets',
            'smartphone',
            'Smartphones, Laptops, Audio Gear & Smart Home Accessories',
            'Cyber Tower Ground Floor, Tech Park Road',
            'TECH AUTHORIZED',
            '#2563EB', # Blue
            'tech_logo.png',
            'https://images.unsplash.com/photo-1550009158-9ebf69173e03?w=800&auto=format&fit=crop&q=80',
            1.0,
            3000.0, # Min purchase ₹3000
            15.0,   # Max 15% discount
            1000.0, # Max ₹1000 off
            30,     # 30 days validity
            1,      # Next day
            'Redeem up to ₹1,000 on gadgets & accessories for purchase >= ₹3,000. Valid 30 days.',
            0,
            now_str
        ),
        (
            'firm-vogue',
            'Urban Vogue Fashion Boutique',
            'Fashion & Apparel',
            'shirt',
            'Designer Menswear, Ethnic Silks, Casual Chic & Kids Couture',
            'Grand Mall, 1st Avenue Promenade',
            'TRENDING FASHION',
            '#DB2777', # Pink/Rose
            'vogue_logo.png',
            'https://images.unsplash.com/photo-1441986300917-64674bd600d8?w=800&auto=format&fit=crop&q=80',
            1.0,
            1200.0, # Min purchase ₹1200
            30.0,   # Up to 30% off
            600.0,
            15,     # 15 days validity
            0,
            'Redeem up to 30% of total bill (Max ₹600) on fashion apparel above ₹1,200.',
            0,
            now_str
        ),
        (
            'firm-aura',
            'Aura Ayurveda & Wellness Care',
            'Healthcare & Pharmacy',
            'heart-pulse',
            'Ayurvedic Medicines, Wellness Supplements & Natural Care',
            'Heritage Square, North End',
            'HERBAL HEALTH',
            '#0D9488', # Teal
            'aura_logo.png',
            'https://images.unsplash.com/photo-1584308666744-24d5c474f2ae?w=800&auto=format&fit=crop&q=80',
            1.0,
            500.0,
            20.0,
            200.0,
            21,
            0,
            'Redeem up to ₹200 on wellness supplements and medicines for orders above ₹500.',
            0,
            now_str
        )
    ]

    cursor.executemany('''
    INSERT INTO firms (id, name, category, category_icon, tagline, address, badge, theme_color,
                       logo_url, banner_url, min_purchase_multiplier, min_bill_amount,
                       max_redemption_pct, max_points_per_txn, validity_days, next_day_redemption_only,
                       rule_summary, is_es_pro, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', firms)

    # 2. Seed Default Customers (including Registered Phone from ES PRO)
    customers = [
        ('9876543210', 'Rahul Sharma', 'rahul.sharma@example.com', '#4F46E5', 'Gold VIP', now_str),
        ('9847012345', 'Priya Nair', 'priya.nair@example.com', '#059669', 'Platinum VIP', now_str),
        ('9895067890', 'Mohammed Shafi', 'shafi.m@example.com', '#EA580C', 'Silver Member', now_str)
    ]
    cursor.executemany('''
    INSERT INTO customers (phone, name, email, avatar_color, vip_tier, created_at)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', customers)

    # 3. Seed Realistic Batches for Rahul Sharma (9876543210)
    # Reflects genuine ES PRO 10x rules, petrol pump visits, cafe bills
    batches = [
        # Batch 1: ES PRO Supermarket (earned 3 days ago, expires in 4 days)
        (
            'BATCH-ES-9821',
            '9876543210',
            'firm-es-pro',
            'INV-ES-2026-9821',
            3200.00,
            320.00, # 320 points earned
            320.00,
            (now - timedelta(days=3)).strftime('%Y-%m-%d %H:%M:%S'),
            (now + timedelta(days=4)).strftime('%Y-%m-%d 23:59:59'),
            3200.00, # 10x purchase rule = ₹3,200 min bill to unlock
            'ACTIVE',
            now_str
        ),
        # Batch 2: ES PRO Supermarket (earned 5 days ago, expires in 2 days - Expiring Soon!)
        (
            'BATCH-ES-8902',
            '9876543210',
            'firm-es-pro',
            'INV-ES-2026-8902',
            1500.00,
            150.00,
            150.00,
            (now - timedelta(days=5)).strftime('%Y-%m-%d %H:%M:%S'),
            (now + timedelta(days=2)).strftime('%Y-%m-%d 23:59:59'),
            1500.00, # 10x purchase rule = ₹1,500 min bill to unlock
            'ACTIVE',
            now_str
        ),
        # Batch 3: Highway Petroleum (earned 2 days ago, expires in 12 days)
        (
            'BATCH-PETRO-410',
            '9876543210',
            'firm-petro',
            'PUMP-TX-6604',
            2200.00,
            110.00,
            110.00,
            (now - timedelta(days=2)).strftime('%Y-%m-%d %H:%M:%S'),
            (now + timedelta(days=12)).strftime('%Y-%m-%d 23:59:59'),
            500.00,
            'ACTIVE',
            now_str
        ),
        # Batch 4: Bean & Bloom Cafe (earned yesterday, expires in 9 days)
        (
            'BATCH-CAFE-312',
            '9876543210',
            'firm-cafe',
            'CAFE-ORD-8819',
            650.00,
            65.00,
            65.00,
            (now - timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S'),
            (now + timedelta(days=9)).strftime('%Y-%m-%d 23:59:59'),
            250.00,
            'ACTIVE',
            now_str
        ),
        # Batch 5: Urban Vogue (earned 6 days ago, expires in 9 days)
        (
            'BATCH-VOGUE-702',
            '9876543210',
            'firm-vogue',
            'VOG-RET-1294',
            2800.00,
            140.00,
            140.00,
            (now - timedelta(days=6)).strftime('%Y-%m-%d %H:%M:%S'),
            (now + timedelta(days=9)).strftime('%Y-%m-%d 23:59:59'),
            1200.00,
            'ACTIVE',
            now_str
        )
    ]

    cursor.executemany('''
    INSERT INTO reward_batches (id, customer_phone, firm_id, invoice_no, bill_amount,
                                points_earned, points_remaining, earned_date, expiry_date,
                                required_bill_to_redeem, status, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', batches)

    # 4. Seed Transaction Ledger History
    txs = [
        (
            'TX-1001',
            '9876543210',
            'firm-es-pro',
            'EARN',
            320.00,
            320.00,
            'INV-ES-2026-9821',
            3200.00,
            'Profit-share Reward Earned at ES Supermarket (ES PRO ERP)',
            'BATCH-ES-9821',
            (now - timedelta(days=3)).strftime('%Y-%m-%d %H:%M:%S')
        ),
        (
            'TX-1002',
            '9876543210',
            'firm-es-pro',
            'EARN',
            150.00,
            150.00,
            'INV-ES-2026-8902',
            1500.00,
            'Monthly Grocery Bill Points at ES Supermarket',
            'BATCH-ES-8902',
            (now - timedelta(days=5)).strftime('%Y-%m-%d %H:%M:%S')
        ),
        (
            'TX-1003',
            '9876543210',
            'firm-petro',
            'EARN',
            110.00,
            110.00,
            'PUMP-TX-6604',
            2200.00,
            'Full-tank Speed Petrol Purchase Cashback',
            'BATCH-PETRO-410',
            (now - timedelta(days=2)).strftime('%Y-%m-%d %H:%M:%S')
        ),
        (
            'TX-1004',
            '9876543210',
            'firm-cafe',
            'EARN',
            65.00,
            65.00,
            'CAFE-ORD-8819',
            650.00,
            'Cappuccino & Croissant Weekend Combo Cashback',
            'BATCH-CAFE-312',
            (now - timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')
        ),
        (
            'TX-1005',
            '9876543210',
            'firm-vogue',
            'EARN',
            140.00,
            140.00,
            'VOG-RET-1294',
            2800.00,
            'Festive Casual Wear Purchase Points',
            'BATCH-VOGUE-702',
            (now - timedelta(days=6)).strftime('%Y-%m-%d %H:%M:%S')
        ),
        (
            'TX-1006',
            '9876543210',
            'firm-cafe',
            'REDEEM',
            -50.00,
            -50.00,
            'CAFE-ORD-7712',
            450.00,
            'Points Redeemed at Bean & Bloom Counter',
            'BATCH-PREV-01',
            (now - timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
        )
    ]
    cursor.executemany('''
    INSERT INTO transactions (id, customer_phone, firm_id, type, points, amount_equivalent,
                             bill_no, bill_amount, description, batch_ids, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', txs)

    # 5. Seed Firm Offers & Targeted Ads
    offers = [
        # ES PRO Offers
        (
            'OFF-ES-01',
            'firm-es-pro',
            'Mega Grocery Weekend - 2X Points!',
            'PROFIT CASHBACK',
            'Purchase fresh farm staples & groceries above ₹2,000 using ready payment and earn double reward points into your centralized wallet!',
            'ESMEGA2X',
            (now + timedelta(days=5)).strftime('%Y-%m-%d'),
            'Double Points on ₹2,000+',
            'https://images.unsplash.com/photo-1542838132-92c53300491e?w=800&auto=format&fit=crop&q=80',
            1,
            now_str
        ),
        (
            'OFF-ES-02',
            'firm-es-pro',
            'ES PRO Smart Unlock Voucher',
            '10x MULTIPLIER SPECIAL',
            'Got expiring batches? Redeem your ES PRO points on your next bill above 10x value and enjoy 100% bill offset!',
            'UNLOCK10X',
            (now + timedelta(days=7)).strftime('%Y-%m-%d'),
            '1 Pt = ₹1 Off',
            'https://images.unsplash.com/photo-1604719312566-8912e9227c6a?w=800&auto=format&fit=crop&q=80',
            0,
            now_str
        ),
        # Petroleum Offers
        (
            'OFF-PETRO-01',
            'firm-petro',
            'Highway Fuel Rush: Free Express Foam Wash',
            'EXCLUSIVE PERK',
            'Fill fuel for ₹2,500 or more, redeem up to ₹150 points instantly, and receive a free robotic express foam wash coupon!',
            'SPEEDCLEAN',
            (now + timedelta(days=10)).strftime('%Y-%m-%d'),
            'Free Car Wash + ₹150 Off',
            'https://images.unsplash.com/photo-1520340356584-f9917d1eea6f?w=800&auto=format&fit=crop&q=80',
            1,
            now_str
        ),
        # Cafe Offers
        (
            'OFF-CAFE-01',
            'firm-cafe',
            'Bean & Bloom Sunset Happy Hours',
            '4 PM - 7 PM DAILY',
            'Enjoy freshly brewed cold brews and artisanal pastries. Redeem your centralized wallet points with no minimum waiting period!',
            'BLOOM20',
            (now + timedelta(days=14)).strftime('%Y-%m-%d'),
            'Flat 20% Bill Offset',
            'https://images.unsplash.com/photo-1517256064527-09c73fc73e38?w=800&auto=format&fit=crop&q=80',
            1,
            now_str
        ),
        # Electronics Offers
        (
            'OFF-TECH-01',
            'firm-nexus',
            'Smartphone Upgrade Fest: ₹1,000 Instant Off',
            'LIMITED STOCK',
            'Exchange your older smartphone or upgrade to latest 5G devices. Use up to 1,000 centralized reward points instantly on billing!',
            'NEXUSUP',
            (now + timedelta(days=20)).strftime('%Y-%m-%d'),
            '₹1,000 Off on 5G Mobiles',
            'https://images.unsplash.com/photo-1511707171634-5f897ff02aa9?w=800&auto=format&fit=crop&q=80',
            0,
            now_str
        ),
        # Fashion Offers
        (
            'OFF-VOGUE-01',
            'firm-vogue',
            'Festive Couture Runway: 30% Privilege Offset',
            'SEASONAL SALE',
            'Refresh your wardrobe with top designer collections. Redeem your OmniPoints on purchases over ₹1,200 at checkout.',
            'VOGUE30',
            (now + timedelta(days=12)).strftime('%Y-%m-%d'),
            'Save Up To ₹600',
            'https://images.unsplash.com/photo-1490481651871-ab68de25d43d?w=800&auto=format&fit=crop&q=80',
            0,
            now_str
        ),
        # Wellness Offers
        (
            'OFF-AURA-01',
            'firm-aura',
            'Winter Immunity & Herbal Health Bonus',
            'HEALTH PACK',
            'Buy Ayurvedic wellness packs or organic healthcare products above ₹800 and earn an extra ₹50 cashback bonus directly to your wallet.',
            'AURAHEALTH',
            (now + timedelta(days=15)).strftime('%Y-%m-%d'),
            '₹50 Bonus Points',
            'https://images.unsplash.com/photo-1540555700478-4be289fbecef?w=800&auto=format&fit=crop&q=80',
            0,
            now_str
        )
    ]
    cursor.executemany('''
    INSERT INTO firm_offers (id, firm_id, title, tag, description, coupon_code,
                             valid_till, discount_text, ad_banner, highlight, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', offers)

    # 6. Seed Scratch Cards (Interactive customer addictive element)
    scratch_cards = [
        ('SC-01', '9876543210', '🎉 Mystery Reward Drop', 25.00, 0, None, now_str),
        ('SC-02', '9876543210', '☕ Cafe Weekend Perk', 15.00, 0, None, now_str),
        ('SC-03', '9876543210', '🛍️ ES PRO First Visit Bonus', 50.00, 1, (now - timedelta(days=10)).strftime('%Y-%m-%d %H:%M:%S'), now_str)
    ]
    cursor.executemany('''
    INSERT INTO scratch_cards (id, customer_phone, title, points_reward, is_scratched, scratched_at, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', scratch_cards)

def seed_firm_profiles(cursor):
    now = datetime.now()
    now_str = now.strftime('%Y-%m-%d %H:%M:%S')

    # Multi-firm customer profiles (Simulating varied name records across partner stores)
    profiles = [
        # Rahul Sharma (9876543210) - Different names across firms!
        ('9876543210', 'firm-es-pro', 'Rahul Sharma', 'ES-PRO-9821', now_str),
        ('9876543210', 'firm-petro', 'Rahul S.', 'PETRO-FL-410', now_str),
        ('9876543210', 'firm-cafe', 'R. Sharma', 'CAFE-BBM-312', now_str),
        ('9876543210', 'firm-nexus', 'Rahul Sharma (Tech)', 'NX-MOB-505', now_str),
        ('9876543210', 'firm-vogue', 'Rahul S.', 'VOG-PR-702', now_str),
        ('9876543210', 'firm-aura', 'Rahul Sharma', 'AURA-HL-109', now_str),

        # Priya Nair (9847012345)
        ('9847012345', 'firm-es-pro', 'Priya Nair', 'ES-PRO-1144', now_str),
        ('9847012345', 'firm-vogue', 'Priya N.', 'VOG-PR-882', now_str),
        ('9847012345', 'firm-aura', 'Priya Manoj', 'AURA-HL-619', now_str),
        ('9847012345', 'firm-cafe', 'Priya Nair', 'CAFE-BBM-220', now_str),

        # Mohammed Shafi (9895067890)
        ('9895067890', 'firm-es-pro', 'Mohammed Shafi', 'ES-PRO-5501', now_str),
        ('9895067890', 'firm-petro', 'M. Shafi', 'PETRO-FL-722', now_str),
        ('9895067890', 'firm-cafe', 'Shafi Calicut', 'CAFE-BBM-104', now_str),

        # Midhilaj (9656360650)
        ('9656360650', 'firm-es-pro', 'Midhilaj', 'ES-PRO-3301', now_str),
        ('9656360650', 'firm-petro', 'Midhilaj P.S.', 'PETRO-FL-890', now_str),
        ('9656360650', 'firm-nexus', 'Midhilaj Tech', 'NX-MOB-411', now_str)
    ]

    cursor.executemany('''
    INSERT OR REPLACE INTO firm_customer_profiles (customer_phone, firm_id, registered_name, account_no, created_at)
    VALUES (?, ?, ?, ?, ?)
    ''', profiles)

    # Invoices & Surrender/Return Slips
    invoices = [
        # Rahul Sharma (9876543210)
        ('INV-ES-2026-9821', '9876543210', 'firm-es-pro', 'PURCHASE', 'INV-ES-2026-9821', 3200.00, 14, 'UPI / GPay', 320.00, 'Groceries & Household Essentials', (now - timedelta(days=3)).strftime('%Y-%m-%d %H:%M:%S'), now_str),
        ('INV-ES-2026-8902', '9876543210', 'firm-es-pro', 'PURCHASE', 'INV-ES-2026-8902', 1500.00, 7, 'Cash', 150.00, 'Fresh Farm Produce & Organic Dairy', (now - timedelta(days=5)).strftime('%Y-%m-%d %H:%M:%S'), now_str),
        ('RET-ES-2026-0104', '9876543210', 'firm-es-pro', 'RETURN', 'RET-ES-2026-0104', 400.00, 1, 'Credit Memo', 0.0, 'Surrendered Defective Blender (Sealed Return)', (now - timedelta(days=2)).strftime('%Y-%m-%d %H:%M:%S'), now_str),

        ('PUMP-TX-6604', '9876543210', 'firm-petro', 'PURCHASE', 'PUMP-TX-6604', 2200.00, 1, 'Credit Card', 110.00, 'High Octane Speed Petrol 21.5L Fill', (now - timedelta(days=2)).strftime('%Y-%m-%d %H:%M:%S'), now_str),
        ('PUMP-TX-5519', '9876543210', 'firm-petro', 'PURCHASE', 'PUMP-TX-5519', 1400.00, 2, 'UPI', 70.00, 'Auto Lubricant Oil + Regular Fuel', (now - timedelta(days=6)).strftime('%Y-%m-%d %H:%M:%S'), now_str),

        ('CAFE-ORD-8819', '9876543210', 'firm-cafe', 'PURCHASE', 'CAFE-ORD-8819', 650.00, 3, 'UPI', 65.00, 'Artisan Cold Brew & Almond Croissants', (now - timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S'), now_str),
        ('CAFE-ORD-7712', '9876543210', 'firm-cafe', 'PURCHASE', 'CAFE-ORD-7712', 450.00, 2, 'Cash', -50.00, 'Espresso & Sourdough Toast (Redeemed ₹50)', (now - timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S'), now_str),

        ('VOG-RET-1294', '9876543210', 'firm-vogue', 'PURCHASE', 'VOG-RET-1294', 2800.00, 2, 'Debit Card', 140.00, 'Designer Silk Kurta & Denim Trousers', (now - timedelta(days=6)).strftime('%Y-%m-%d %H:%M:%S'), now_str),
        ('RET-VOG-2026-0082', '9876543210', 'firm-vogue', 'RETURN', 'RET-VOG-2026-0082', 250.00, 1, 'Store Credit', 0.0, 'Surrendered Apparel Size Exchange Adjustment', (now - timedelta(days=4)).strftime('%Y-%m-%d %H:%M:%S'), now_str),

        ('NEX-INV-4401', '9876543210', 'firm-nexus', 'PURCHASE', 'NEX-INV-4401', 3500.00, 2, 'Credit Card', 175.00, 'Wireless ANC Earbuds & Type-C Fast Charger', (now - timedelta(days=8)).strftime('%Y-%m-%d %H:%M:%S'), now_str),
        ('AURA-INV-1102', '9876543210', 'firm-aura', 'PURCHASE', 'AURA-INV-1102', 850.00, 3, 'UPI', 42.50, 'Ayurvedic Herbal Immunity Pack & Syrups', (now - timedelta(days=9)).strftime('%Y-%m-%d %H:%M:%S'), now_str),

        # Priya Nair (9847012345)
        ('INV-ES-PR-01', '9847012345', 'firm-es-pro', 'PURCHASE', 'INV-ES-PR-01', 4200.00, 18, 'UPI', 420.00, 'Monthly Organic Grocery Cart', (now - timedelta(days=2)).strftime('%Y-%m-%d %H:%M:%S'), now_str),
        ('RET-ES-PR-01', '9847012345', 'firm-es-pro', 'RETURN', 'RET-ES-PR-01', 300.00, 1, 'Cash Refund', 0.0, 'Surrendered Duplicate Grocery Item', (now - timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S'), now_str),
        ('VOG-PR-01', '9847012345', 'firm-vogue', 'PURCHASE', 'VOG-PR-01', 3100.00, 3, 'Card', 155.00, 'Festive Saree Collection', (now - timedelta(days=4)).strftime('%Y-%m-%d %H:%M:%S'), now_str),

        # Mohammed Shafi (9895067890)
        ('INV-ES-SH-01', '9895067890', 'firm-es-pro', 'PURCHASE', 'INV-ES-SH-01', 1900.00, 8, 'Cash', 190.00, 'Weekly Grocery Essentials', (now - timedelta(days=3)).strftime('%Y-%m-%d %H:%M:%S'), now_str),
        ('PETRO-SH-01', '9895067890', 'firm-petro', 'PURCHASE', 'PETRO-SH-01', 2500.00, 1, 'UPI', 125.00, 'Commercial Van Diesel Full Fill', (now - timedelta(days=2)).strftime('%Y-%m-%d %H:%M:%S'), now_str)
    ]

    cursor.executemany('''
    INSERT OR REPLACE INTO firm_invoices (id, customer_phone, firm_id, invoice_type, invoice_no, amount, items_count, payment_mode, points_affected, notes, invoice_date, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', invoices)

# ----------------- HELPER FUNCTIONS ----------------- #

def check_and_update_batch_status(cursor=None, conn=None):
    """Periodically lapse expired batches in background"""
    pass

def calculate_customer_summary(phone):
    conn = get_db()
    cursor = conn.cursor()
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Total active points
    cursor.execute('''
    SELECT COALESCE(SUM(points_remaining), 0)
    FROM reward_batches
    WHERE customer_phone = ? AND status = 'ACTIVE' AND points_remaining > 0 AND expiry_date >= ?
    ''', (phone, now_str))
    total_active_points = float(cursor.fetchone()[0])

    # Expiring within 48 hours
    exp_48h = (datetime.now() + timedelta(hours=48)).strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute('''
    SELECT COALESCE(SUM(points_remaining), 0)
    FROM reward_batches
    WHERE customer_phone = ? AND status = 'ACTIVE' AND points_remaining > 0 AND expiry_date <= ?
    ''', (phone, exp_48h))
    expiring_soon_points = float(cursor.fetchone()[0])

    # Lifetime earned
    cursor.execute('''
    SELECT COALESCE(SUM(points), 0)
    FROM transactions
    WHERE customer_phone = ? AND type IN ('EARN', 'BONUS')
    ''', (phone,))
    lifetime_earned = float(cursor.fetchone()[0])

    # Lifetime redeemed
    cursor.execute('''
    SELECT COALESCE(SUM(ABS(points)), 0)
    FROM transactions
    WHERE customer_phone = ? AND type = 'REDEEM'
    ''', (phone,))
    lifetime_redeemed = float(cursor.fetchone()[0])

    # Unscratched rewards count
    cursor.execute('''
    SELECT COUNT(*) FROM scratch_cards
    WHERE customer_phone = ? AND is_scratched = 0
    ''', (phone,))
    unopened_cards = int(cursor.fetchone()[0])

    conn.close()

    return {
        'total_active_points': round(total_active_points, 2),
        'total_value_inr': round(total_active_points, 2), # 1 Pt = ₹1
        'expiring_soon_points': round(expiring_soon_points, 2),
        'lifetime_earned': round(lifetime_earned, 2),
        'lifetime_redeemed': round(lifetime_redeemed, 2),
        'unopened_cards': unopened_cards
    }

def get_customer_business_ledger(phone):
    """
    Computes complete multi-firm business ledger:
    - Overall purchase bills count, total gross purchases, goods surrendered / returned, net purchases
    - Firm-by-firm breakdown with store registered name, invoices count, gross purchase, return surrender, net purchase, and active points
    - Full itemized list of invoices and return credit slips
    """
    conn = get_db()
    cursor = conn.cursor()

    # 1. Overall Metrics across all firms
    cursor.execute('''
    SELECT 
        COUNT(CASE WHEN invoice_type = 'PURCHASE' THEN 1 END) as total_invoices_count,
        COALESCE(SUM(CASE WHEN invoice_type = 'PURCHASE' THEN amount ELSE 0 END), 0) as total_purchases_amount,
        COUNT(CASE WHEN invoice_type = 'RETURN' THEN 1 END) as total_returns_count,
        COALESCE(SUM(CASE WHEN invoice_type = 'RETURN' THEN amount ELSE 0 END), 0) as total_returns_amount
    FROM firm_invoices
    WHERE customer_phone = ?
    ''', (phone,))
    row = cursor.fetchone()
    total_invoices_count = int(row['total_invoices_count'] or 0)
    total_purchases_amount = round(float(row['total_purchases_amount'] or 0), 2)
    total_returns_count = int(row['total_returns_count'] or 0)
    total_returns_amount = round(float(row['total_returns_amount'] or 0), 2)
    net_purchases_amount = round(total_purchases_amount - total_returns_amount, 2)

    # Lifetime points earned and redeemed
    cursor.execute('''
    SELECT 
        COALESCE(SUM(CASE WHEN type IN ('EARN', 'BONUS') THEN points ELSE 0 END), 0) as earned,
        COALESCE(SUM(CASE WHEN type = 'REDEEM' THEN ABS(points) ELSE 0 END), 0) as redeemed
    FROM transactions
    WHERE customer_phone = ?
    ''', (phone,))
    tx_row = cursor.fetchone()
    points_earned = round(float(tx_row['earned'] or 0), 2)
    points_redeemed = round(float(tx_row['redeemed'] or 0), 2)

    # Active wallet points
    cursor.execute('''
    SELECT COALESCE(SUM(points_remaining), 0)
    FROM reward_batches
    WHERE customer_phone = ? AND status = 'ACTIVE' AND points_remaining > 0
    ''', (phone,))
    active_points = round(float(cursor.fetchone()[0] or 0), 2)

    overall = {
        'total_invoices_count': total_invoices_count,
        'total_purchases_amount': total_purchases_amount,
        'total_returns_count': total_returns_count,
        'total_returns_amount': total_returns_amount,
        'net_purchases_amount': net_purchases_amount,
        'points_earned': points_earned,
        'points_redeemed': points_redeemed,
        'active_points': active_points
    }

    # 2. Per-Firm Breakdown
    cursor.execute('SELECT * FROM firms ORDER BY is_es_pro DESC, name ASC')
    firms = [dict(f) for f in cursor.fetchall()]

    firms_ledger = []
    for f in firms:
        firm_id = f['id']

        # Get registered name at this firm if any
        cursor.execute('''
        SELECT registered_name, account_no FROM firm_customer_profiles
        WHERE customer_phone = ? AND firm_id = ?
        ''', (phone, firm_id))
        prof = cursor.fetchone()
        reg_name = prof['registered_name'] if prof else None
        acc_no = prof['account_no'] if prof else None

        # Get firm invoices summary
        cursor.execute('''
        SELECT 
            COUNT(CASE WHEN invoice_type = 'PURCHASE' THEN 1 END) as invoices_count,
            COALESCE(SUM(CASE WHEN invoice_type = 'PURCHASE' THEN amount ELSE 0 END), 0) as purchases_amount,
            COUNT(CASE WHEN invoice_type = 'RETURN' THEN 1 END) as returns_count,
            COALESCE(SUM(CASE WHEN invoice_type = 'RETURN' THEN amount ELSE 0 END), 0) as returns_amount
        FROM firm_invoices
        WHERE customer_phone = ? AND firm_id = ?
        ''', (phone, firm_id))
        inv_summary = cursor.fetchone()
        f_inv_count = int(inv_summary['invoices_count'] or 0)
        f_purchases = round(float(inv_summary['purchases_amount'] or 0), 2)
        f_returns_count = int(inv_summary['returns_count'] or 0)
        f_returns = round(float(inv_summary['returns_amount'] or 0), 2)
        f_net = round(f_purchases - f_returns, 2)

        # Get firm active points
        cursor.execute('''
        SELECT COALESCE(SUM(points_remaining), 0)
        FROM reward_batches
        WHERE customer_phone = ? AND firm_id = ? AND status = 'ACTIVE' AND points_remaining > 0
        ''', (phone, firm_id))
        f_pts = round(float(cursor.fetchone()[0] or 0), 2)

        # Get all invoices for this firm
        cursor.execute('''
        SELECT * FROM firm_invoices
        WHERE customer_phone = ? AND firm_id = ?
        ORDER BY invoice_date DESC
        ''', (phone, firm_id))
        invoices_list = [dict(r) for r in cursor.fetchall()]

        # Only include in ledger if customer has interaction or profile with this firm
        has_activity = (f_inv_count > 0 or f_returns_count > 0 or f_pts > 0 or reg_name is not None)
        if has_activity:
            firms_ledger.append({
                'firm_id': firm_id,
                'firm_name': f['name'],
                'firm_category': f['category'],
                'category_icon': f['category_icon'],
                'theme_color': f['theme_color'],
                'badge': f['badge'],
                'is_es_pro': f['is_es_pro'],
                'registered_name': reg_name,
                'account_no': acc_no,
                'invoices_count': f_inv_count,
                'purchases_amount': f_purchases,
                'returns_count': f_returns_count,
                'returns_amount': f_returns,
                'net_amount': f_net,
                'points_remaining': f_pts,
                'invoices': invoices_list
            })

    conn.close()
    return {
        'overall': overall,
        'firms_ledger': firms_ledger
    }

# ----------------- API ROUTES ----------------- #

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/manifest.json')
def serve_manifest():
    return send_from_directory('static', 'manifest.json')

@app.route('/sw.js')
def serve_sw():
    return send_from_directory('static', 'sw.js', mimetype='application/javascript')

@app.route('/api/customers', methods=['GET'])
def list_customers():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
    SELECT c.phone, c.name, c.email, c.avatar_color, c.vip_tier,
           COUNT(DISTINCT i.id) as es_invoices_count,
           COALESCE(SUM(b.points_remaining), 0) as es_points
    FROM customers c
    LEFT JOIN firm_invoices i ON c.phone = i.customer_phone AND i.firm_id = 'firm-es-pro'
    LEFT JOIN reward_batches b ON c.phone = b.customer_phone AND b.firm_id = 'firm-es-pro' AND b.status = 'ACTIVE'
    GROUP BY c.phone
    ORDER BY es_invoices_count DESC, c.id ASC
    ''')
    customers = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({'success': True, 'customers': customers})

@app.route('/api/auth/login', methods=['POST'])
def login_or_register():
    data = request.json or {}
    phone = str(data.get('phone', '')).strip().replace('+91', '').replace(' ', '').replace('-', '')
    name = data.get('name', '').strip()

    if not phone or len(phone) < 10:
        return jsonify({'success': False, 'message': 'Please provide a valid 10-digit mobile number'}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM customers WHERE phone = ?', (phone,))
    user = cursor.fetchone()

    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    if not user:
        # Auto register customer with welcome bonus
        customer_name = name if name else f"Customer {phone[-4:]}"
        avatar_colors = ['#4F46E5', '#059669', '#EA580C', '#2563EB', '#DB2777', '#7C3AED']
        color = random.choice(avatar_colors)
        cursor.execute('''
        INSERT INTO customers (phone, name, email, avatar_color, vip_tier, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ''', (phone, customer_name, f"{phone}@rewards.espro", color, 'Silver', now_str))

        # Welcome bonus scratch card!
        cursor.execute('''
        INSERT INTO scratch_cards (id, customer_phone, title, points_reward, is_scratched, created_at)
        VALUES (?, ?, ?, ?, 0, ?)
        ''', (f"SC-WEL-{int(time.time())}", phone, '🎁 Welcome Gift Bonus Card', 50.00, now_str))

        conn.commit()
        cursor.execute('SELECT * FROM customers WHERE phone = ?', (phone,))
        user = cursor.fetchone()

    user_dict = dict(user)
    conn.close()

    summary = calculate_customer_summary(phone)
    ledger = get_customer_business_ledger(phone)
    return jsonify({
        'success': True,
        'customer': user_dict,
        'summary': summary,
        'business_ledger': ledger
    })

@app.route('/api/auth/request-otp', methods=['POST'])
def auth_request_otp():
    """
    Step 1 of Phone Login:
    Accepts customer 10-digit phone number.
    Fetches all registered names across partner firms.
    Generates 6-digit OTP and detects if name divergence exists across businesses.
    """
    data = request.json or {}
    phone = str(data.get('phone', '')).strip().replace('+91', '').replace(' ', '').replace('-', '')

    if not phone or len(phone) < 10:
        return jsonify({'success': False, 'message': 'Please enter a valid 10-digit mobile number'}), 400

    conn = get_db()
    cursor = conn.cursor()

    # Query multi-firm profiles for this phone
    cursor.execute('''
    SELECT p.*, f.name as firm_name, f.category as firm_category, f.theme_color, f.badge
    FROM firm_customer_profiles p
    JOIN firms f ON p.firm_id = f.id
    WHERE p.customer_phone = ?
    ORDER BY f.is_es_pro DESC, f.name ASC
    ''', (phone,))
    firm_profiles = [dict(row) for row in cursor.fetchall()]

    # Also check if existing central customer record exists
    cursor.execute('SELECT * FROM customers WHERE phone = ?', (phone,))
    existing_customer = cursor.fetchone()
    current_central_name = existing_customer['name'] if existing_customer else None

    # Collect distinct registered names across firms
    distinct_names = []
    for fp in firm_profiles:
        nm = fp['registered_name'].strip()
        if nm and nm not in distinct_names:
            distinct_names.append(nm)

    if current_central_name and current_central_name not in distinct_names:
        distinct_names.insert(0, current_central_name)

    # Fallback default name
    default_name = current_central_name or (distinct_names[0] if distinct_names else f"Customer {phone[-4:]}")

    # Generate 6-digit OTP
    otp = f"{random.randint(100000, 999999)}"
    now = datetime.now()
    now_str = now.strftime('%Y-%m-%d %H:%M:%S')
    exp_str = (now + timedelta(minutes=10)).strftime('%Y-%m-%d %H:%M:%S')

    # Store OTP in DB
    cursor.execute('''
    INSERT OR REPLACE INTO otp_verifications (phone, otp, created_at, expires_at)
    VALUES (?, ?, ?, ?)
    ''', (phone, otp, now_str, exp_str))
    conn.commit()
    conn.close()

    has_divergence = len(distinct_names) > 1

    return jsonify({
        'success': True,
        'message': f"OTP successfully sent to +91 {phone}",
        'phone': phone,
        'demo_otp': otp,
        'has_name_divergence': has_divergence,
        'distinct_names': distinct_names,
        'firm_profiles': firm_profiles,
        'current_central_name': current_central_name,
        'default_selected_name': default_name
    })

@app.route('/api/auth/verify-otp', methods=['POST'])
def auth_verify_otp():
    """
    Step 2 of Phone Login:
    Verifies 6-digit OTP and establishes customer's chosen Centralized Profile Name!
    Updates the customer's centralized profile across all connected firms.
    """
    data = request.json or {}
    phone = str(data.get('phone', '')).strip().replace('+91', '').replace(' ', '').replace('-', '')
    entered_otp = str(data.get('otp', '')).strip()
    selected_name = str(data.get('selected_name', '')).strip()
    custom_name = str(data.get('custom_name', '')).strip()

    if not phone or len(phone) < 10:
        return jsonify({'success': False, 'message': 'Invalid mobile number'}), 400

    if not entered_otp:
        return jsonify({'success': False, 'message': 'Please enter the 6-digit OTP'}), 400

    conn = get_db()
    cursor = conn.cursor()

    # Verify OTP against stored value or master demo codes (123456, 849201)
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute('SELECT * FROM otp_verifications WHERE phone = ?', (phone,))
    stored = cursor.fetchone()

    is_valid = False
    if entered_otp in ['123456', '849201']: # Master test codes
        is_valid = True
    elif stored and stored['otp'] == entered_otp and stored['expires_at'] >= now_str:
        is_valid = True

    if not is_valid:
        conn.close()
        return jsonify({'success': False, 'message': 'Invalid or expired OTP. Please try again.'}), 400

    # Determine final preferred name chosen by customer
    preferred_name = custom_name if custom_name else (selected_name if selected_name else f"Customer {phone[-4:]}")

    # Check if customer exists in customers table
    cursor.execute('SELECT * FROM customers WHERE phone = ?', (phone,))
    user = cursor.fetchone()

    if user:
        # Update name to chosen centralized name
        cursor.execute('UPDATE customers SET name = ? WHERE phone = ?', (preferred_name, phone))
        conn.commit()
    else:
        # Auto-register new customer with welcome card
        avatar_colors = ['#4F46E5', '#059669', '#EA580C', '#2563EB', '#DB2777', '#7C3AED']
        color = random.choice(avatar_colors)
        cursor.execute('''
        INSERT INTO customers (phone, name, email, avatar_color, vip_tier, created_at)
        VALUES (?, ?, ?, ?, 'Silver', ?)
        ''', (phone, preferred_name, f"{phone}@rewards.espro", color, now_str))

        cursor.execute('''
        INSERT INTO scratch_cards (id, customer_phone, title, points_reward, is_scratched, created_at)
        VALUES (?, ?, '🎁 Welcome Gift Bonus Card', 50.00, 0, ?)
        ''', (f"SC-WEL-{int(time.time())}", phone, now_str))
        conn.commit()

    # Re-fetch customer
    cursor.execute('SELECT * FROM customers WHERE phone = ?', (phone,))
    customer_dict = dict(cursor.fetchone())

    # Clear used OTP
    cursor.execute('DELETE FROM otp_verifications WHERE phone = ?', (phone,))
    conn.commit()
    conn.close()

    summary = calculate_customer_summary(phone)
    ledger = get_customer_business_ledger(phone)

    return jsonify({
        'success': True,
        'message': f"Welcome, {preferred_name}! Your profile is now centralized across all connected firms.",
        'customer': customer_dict,
        'summary': summary,
        'business_ledger': ledger
    })

@app.route('/api/customer/<phone>/business-ledger', methods=['GET'])
def get_customer_ledger_endpoint(phone):
    """Returns comprehensive multi-firm business ledger & invoice summary"""
    phone = str(phone).strip().replace('+91', '').replace(' ', '').replace('-', '')
    ledger = get_customer_business_ledger(phone)
    return jsonify({'success': True, 'business_ledger': ledger})

@app.route('/api/v1/erp/record-return', methods=['POST'])
def erp_record_return():
    """
    Standardized API called when a customer returns / surrenders goods at any partner firm.
    Inserts a RETURN invoice and creates an audit transaction in the centralized passbook.
    """
    data = request.json or {}
    phone = str(data.get('phone', '')).strip().replace('+91', '').replace(' ', '').replace('-', '')
    firm_id = data.get('firm_id', 'firm-es-pro')
    return_slip_no = data.get('return_slip_no', f"RET-{int(time.time())}")
    original_invoice_no = data.get('original_invoice_no', '')
    return_amount = float(data.get('return_amount', 0))
    reason = data.get('reason', 'Customer goods return / surrender')

    if not phone or len(phone) < 10 or return_amount <= 0:
        return jsonify({'success': False, 'message': 'Valid 10-digit phone and positive return amount required'}), 400

    conn = get_db()
    cursor = conn.cursor()
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Verify firm
    cursor.execute('SELECT name FROM firms WHERE id = ?', (firm_id,))
    firm_row = cursor.fetchone()
    firm_name = firm_row['name'] if firm_row else 'Partner Store'

    # Insert Return invoice
    cursor.execute('''
    INSERT OR REPLACE INTO firm_invoices (id, customer_phone, firm_id, invoice_type, invoice_no, amount, items_count, payment_mode, points_affected, notes, invoice_date, created_at)
    VALUES (?, ?, ?, 'RETURN', ?, ?, 1, 'Credit Memo', 0.0, ?, ?, ?)
    ''', (return_slip_no, phone, firm_id, return_slip_no, return_amount, f"{reason} (Ref: {original_invoice_no})", now_str, now_str))

    # Add audit ledger transaction
    tx_id = f"TX-RET-{int(time.time())}"
    cursor.execute('''
    INSERT INTO transactions (id, customer_phone, firm_id, type, points, amount_equivalent, bill_no, bill_amount, description, batch_ids, created_at)
    VALUES (?, ?, ?, 'RETURN', 0.0, ?, ?, ?, ?, '', ?)
    ''', (tx_id, phone, firm_id, return_amount, return_slip_no, return_amount, f"Surrender / Goods Return Slip #{return_slip_no} at {firm_name} (₹{return_amount:.2f})", now_str))

    conn.commit()
    conn.close()

    ledger = get_customer_business_ledger(phone)
    return jsonify({
        'success': True,
        'message': f"Return slip #{return_slip_no} for ₹{return_amount:.2f} successfully recorded at {firm_name}!",
        'business_ledger': ledger
    })

@app.route('/api/wallet/<phone>', methods=['GET'])
def get_customer_wallet(phone):
    phone = str(phone).strip()
    conn = get_db()
    cursor = conn.cursor()
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    cursor.execute('SELECT * FROM customers WHERE phone = ?', (phone,))
    customer = cursor.fetchone()
    if not customer:
        conn.close()
        return jsonify({'success': False, 'message': 'Customer not registered in ERP network'}), 404

    # Fetch Batches grouped / ordered
    cursor.execute('''
    SELECT b.*, f.name as firm_name, f.category as firm_category, f.badge as firm_badge,
           f.theme_color as firm_theme_color, f.min_purchase_multiplier, f.next_day_redemption_only
    FROM reward_batches b
    JOIN firms f ON b.firm_id = f.id
    WHERE b.customer_phone = ? AND b.status = 'ACTIVE' AND b.points_remaining > 0 AND b.expiry_date >= ?
    ORDER BY b.expiry_date ASC
    ''', (phone, now_str))
    batches = [dict(row) for row in cursor.fetchall()]

    # Format batch countdowns & maturing status
    now = datetime.now()
    for b in batches:
        exp_dt = datetime.strptime(b['expiry_date'], '%Y-%m-%d %H:%M:%S' if ' ' in b['expiry_date'] else '%Y-%m-%d')
        days_left = (exp_dt - now).total_seconds() / 86400.0
        b['days_left'] = max(0, round(days_left, 1))
        b['is_expiring_soon'] = days_left <= 2.0
        
        # Check Next-day redemption policy (ES PRO Rule)
        earned_dt = datetime.strptime(b['earned_date'], '%Y-%m-%d %H:%M:%S' if ' ' in b['earned_date'] else '%Y-%m-%d')
        is_same_day = (earned_dt.date() == now.date())
        b['is_locked_next_day'] = bool(b['next_day_redemption_only'] and is_same_day)

    # Fetch Firm Summary (Points breakdown by business firm)
    cursor.execute('''
    SELECT f.id as firm_id, f.name as firm_name, f.category as firm_category, f.theme_color, f.badge, f.is_es_pro,
           COALESCE(SUM(b.points_remaining), 0) as total_firm_points,
           COUNT(b.id) as batch_count
    FROM firms f
    LEFT JOIN reward_batches b ON f.id = b.firm_id AND b.customer_phone = ? AND b.status = 'ACTIVE' AND b.points_remaining > 0
    GROUP BY f.id
    ORDER BY total_firm_points DESC
    ''', (phone,))
    firm_breakdowns = [dict(row) for row in cursor.fetchall()]

    # Fetch recent transactions
    cursor.execute('''
    SELECT t.*, f.name as firm_name, f.category as firm_category, f.theme_color
    FROM transactions t
    JOIN firms f ON t.firm_id = f.id
    WHERE t.customer_phone = ?
    ORDER BY t.created_at DESC
    LIMIT 25
    ''', (phone,))
    transactions = [dict(row) for row in cursor.fetchall()]

    # Fetch Scratch cards
    cursor.execute('''
    SELECT * FROM scratch_cards
    WHERE customer_phone = ?
    ORDER BY is_scratched ASC, created_at DESC
    ''', (phone,))
    scratch_cards = [dict(row) for row in cursor.fetchall()]

    conn.close()

    summary = calculate_customer_summary(phone)
    business_ledger = get_customer_business_ledger(phone)

    return jsonify({
        'success': True,
        'customer': dict(customer),
        'summary': summary,
        'business_ledger': business_ledger,
        'batches': batches,
        'firm_breakdowns': firm_breakdowns,
        'transactions': transactions,
        'scratch_cards': scratch_cards
    })

@app.route('/api/firms', methods=['GET'])
def get_firms():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM firms ORDER BY is_es_pro DESC, name ASC')
    firms = [dict(row) for row in cursor.fetchall()]

    # Add active offers for each firm
    for f in firms:
        cursor.execute('''
        SELECT * FROM firm_offers
        WHERE firm_id = ?
        ORDER BY highlight DESC, created_at DESC
        ''', (f['id'],))
        f['offers'] = [dict(row) for row in cursor.fetchall()]

    conn.close()
    return jsonify({'success': True, 'firms': firms})

@app.route('/api/firms/<firm_id>', methods=['GET'])
def get_firm_details(firm_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM firms WHERE id = ?', (firm_id,))
    firm = cursor.fetchone()
    if not firm:
        conn.close()
        return jsonify({'success': False, 'message': 'Firm not found'}), 404

    firm_dict = dict(firm)
    cursor.execute('SELECT * FROM firm_offers WHERE firm_id = ? ORDER BY highlight DESC', (firm_id,))
    firm_dict['offers'] = [dict(row) for row in cursor.fetchall()]

    # Also retrieve any customer specific batches if phone param provided
    phone = request.args.get('phone')
    if phone:
        cursor.execute('''
        SELECT * FROM reward_batches
        WHERE firm_id = ? AND customer_phone = ? AND status = 'ACTIVE' AND points_remaining > 0
        ORDER BY expiry_date ASC
        ''', (firm_id, phone))
        firm_dict['customer_batches'] = [dict(row) for row in cursor.fetchall()]

    conn.close()
    return jsonify({'success': True, 'firm': firm_dict})

# ----------------- REDEMPTION ENGINE ----------------- #

@app.route('/api/redemption/create-token', methods=['POST'])
def create_redemption_token():
    """
    Generates a secure dynamic QR Code & 6-digit OTP for in-store cashier scanning.
    Validates against the target firm's business rules.
    """
    data = request.json or {}
    phone = data.get('phone')
    firm_id = data.get('firm_id')
    points_to_redeem = float(data.get('points', 0))
    selected_batch_ids = data.get('batch_ids', [])

    if not phone or not firm_id or points_to_redeem <= 0:
        return jsonify({'success': False, 'message': 'Invalid redemption request parameters'}), 400

    conn = get_db()
    cursor = conn.cursor()

    # Verify firm exists
    cursor.execute('SELECT * FROM firms WHERE id = ?', (firm_id,))
    firm = cursor.fetchone()
    if not firm:
        conn.close()
        return jsonify({'success': False, 'message': 'Invalid firm specified'}), 404
    firm = dict(firm)

    # Check available points in wallet
    cursor.execute('''
    SELECT COALESCE(SUM(points_remaining), 0)
    FROM reward_batches
    WHERE customer_phone = ? AND status = 'ACTIVE' AND points_remaining > 0
    ''', (phone,))
    total_avail = float(cursor.fetchone()[0])

    if points_to_redeem > total_avail:
        conn.close()
        return jsonify({'success': False, 'message': f'Insufficient points. Maximum available: {total_avail:.2f}'}), 400

    # Verify firm limits
    if points_to_redeem > firm['max_points_per_txn']:
        conn.close()
        return jsonify({'success': False, 'message': f"Maximum {firm['max_points_per_txn']} points can be redeemed in one transaction at {firm['name']}"}), 400

    # Generate 6-digit OTP and unique token
    otp = f"{random.randint(100000, 999999)}"
    token = f"RP-{int(time.time())}-{random.randint(100, 999)}"
    expires_at = (datetime.now() + timedelta(minutes=5)).strftime('%Y-%m-%d %H:%M:%S')

    cursor.execute('''
    INSERT INTO redemption_tokens (token, otp, customer_phone, firm_id, points_to_redeem, selected_batches, expires_at, status)
    VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING')
    ''', (token, otp, phone, firm_id, points_to_redeem, json.dumps(selected_batch_ids), expires_at))

    conn.commit()
    conn.close()

    return jsonify({
        'success': True,
        'token': token,
        'otp': otp,
        'points_to_redeem': points_to_redeem,
        'value_inr': points_to_redeem,
        'firm_name': firm['name'],
        'expires_at': expires_at,
        'rule_summary': firm['rule_summary'],
        'min_purchase_multiplier': firm['min_purchase_multiplier'],
        'min_bill_amount': firm['min_bill_amount']
    })

@app.route('/api/redemption/cashier-verify', methods=['POST'])
def cashier_verify_and_deduct():
    """
    Simulates the Store POS Cashier Counter executing redemption against the firm's rules!
    Immediately deducts points from customer's batches and updates wallet balance.
    """
    data = request.json or {}
    otp_or_token = str(data.get('code', '')).strip()
    bill_amount = float(data.get('bill_amount', 0))
    cashier_notes = data.get('notes', 'Store POS Counter Redemption')

    if not otp_or_token or bill_amount <= 0:
        return jsonify({'success': False, 'message': 'Please enter a valid bill amount and OTP/Token'}), 400

    conn = get_db()
    cursor = conn.cursor()

    # Look up token by OTP or token ID
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute('''
    SELECT t.*, f.name as firm_name, f.min_purchase_multiplier, f.min_bill_amount,
           f.max_redemption_pct, f.max_points_per_txn, f.next_day_redemption_only, c.name as customer_name
    FROM redemption_tokens t
    JOIN firms f ON t.firm_id = f.id
    JOIN customers c ON t.customer_phone = c.phone
    WHERE (t.otp = ? OR t.token = ?) AND t.status = 'PENDING'
    ''', (otp_or_token, otp_or_token))
    
    token_row = cursor.fetchone()
    if not token_row:
        conn.close()
        return jsonify({'success': False, 'message': 'Invalid, already used, or expired redemption token/OTP.'}), 400

    token = dict(token_row)

    if token['expires_at'] < now_str:
        cursor.execute("UPDATE redemption_tokens SET status = 'EXPIRED' WHERE token = ?", (token['token'],))
        conn.commit()
        conn.close()
        return jsonify({'success': False, 'message': 'Redemption code has expired. Please generate a new code.'}), 400

    points_to_deduct = token['points_to_redeem']
    firm_id = token['firm_id']
    phone = token['customer_phone']

    # 1. Enforce Firm Minimum Bill Amount
    if bill_amount < token['min_bill_amount']:
        conn.close()
        return jsonify({
            'success': False,
            'message': f"Rule Violation: Minimum bill amount of ₹{token['min_bill_amount']:.2f} is required at {token['firm_name']}."
        }), 400

    # 2. Enforce ES PRO 10x Multiplier Rule (if multiplier > 1)
    if token['min_purchase_multiplier'] > 1.0:
        required_min_bill = points_to_deduct * token['min_purchase_multiplier']
        if bill_amount < required_min_bill:
            conn.close()
            return jsonify({
                'success': False,
                'message': f"ES PRO 10x Rule Violation: Current bill ₹{bill_amount:.2f} is lower than required ₹{required_min_bill:.2f} (10x purchase rule)."
            }), 400

    # 3. Enforce Max % of bill discount rule
    max_discount_allowed = (token['max_redemption_pct'] / 100.0) * bill_amount
    if points_to_deduct > max_discount_allowed:
        conn.close()
        return jsonify({
            'success': False,
            'message': f"Rule Violation: Maximum {token['max_redemption_pct']}% of bill (₹{max_discount_allowed:.2f}) can be offset at {token['firm_name']}."
        }), 400

    # 4. Deduct points from active batches using FIFO (oldest expiring first)
    cursor.execute('''
    SELECT * FROM reward_batches
    WHERE customer_phone = ? AND status = 'ACTIVE' AND points_remaining > 0
    ORDER BY expiry_date ASC
    ''', (phone,))
    active_batches = [dict(r) for r in cursor.fetchall()]

    needed = points_to_deduct
    batches_affected = []

    for batch in active_batches:
        if needed <= 0:
            break
        available_in_batch = batch['points_remaining']
        deduct_from_batch = min(needed, available_in_batch)
        new_remaining = available_in_batch - deduct_from_batch
        new_status = 'REDEEMED' if new_remaining <= 0.001 else 'ACTIVE'

        cursor.execute('''
        UPDATE reward_batches
        SET points_remaining = ?, status = ?
        WHERE id = ?
        ''', (new_remaining, new_status, batch['id']))

        batches_affected.append({
            'batch_id': batch['id'],
            'invoice_no': batch['invoice_no'],
            'deducted': deduct_from_batch,
            'remaining': new_remaining
        })
        needed -= deduct_from_batch

    if needed > 0.01:
        conn.rollback()
        conn.close()
        return jsonify({'success': False, 'message': 'Insufficient active points found during batch deduction.'}), 400

    # 5. Record Transaction in Ledger
    tx_id = f"TX-RED-{int(time.time())}-{random.randint(100, 999)}"
    cursor.execute('''
    INSERT INTO transactions (id, customer_phone, firm_id, type, points, amount_equivalent,
                             bill_no, bill_amount, description, batch_ids, created_at)
    VALUES (?, ?, ?, 'REDEEM', ?, ?, ?, ?, ?, ?, ?)
    ''', (
        tx_id,
        phone,
        firm_id,
        -points_to_deduct,
        -points_to_deduct,
        f"POS-{random.randint(10000, 99999)}",
        bill_amount,
        f"Redeemed ₹{points_to_deduct:.2f} at {token['firm_name']} counter ({cashier_notes})",
        json.dumps([b['batch_id'] for b in batches_affected]),
        now_str
    ))

    # 6. Mark token as COMPLETED
    cursor.execute('''
    UPDATE redemption_tokens
    SET status = 'COMPLETED'
    WHERE token = ?
    ''', (token['token'],))

    conn.commit()
    conn.close()

    summary = calculate_customer_summary(phone)

    return jsonify({
        'success': True,
        'message': f"Successfully deducted ₹{points_to_deduct:.2f} from {token['customer_name']}'s wallet!",
        'customer_name': token['customer_name'],
        'points_deducted': points_to_deduct,
        'bill_amount': bill_amount,
        'final_payable_amount': max(0.0, bill_amount - points_to_deduct),
        'remaining_wallet_balance': summary['total_active_points'],
        'transaction_id': tx_id,
        'firm_name': token['firm_name'],
        'batches_affected': batches_affected
    })

# ----------------- LIVE ERP REWARD CLAIM & REDUCTION ----------------- #

@app.route('/api/redemption/claim', methods=['POST'])
def create_redemption_claim():
    """
    Called when a customer clicks 'Redeem Now' (റെഡീം നൗ) on a reward in OmniPoints.
    Dispatches a pending redemption claim directly to the store's billing desk!
    """
    data = request.json or {}
    phone = str(data.get('phone', '')).strip().replace('+91', '').replace(' ', '').replace('-', '')
    firm_id = data.get('firm_id', 'firm-es-pro')
    points = float(data.get('points', 0))
    batch_id = data.get('batch_id', '')
    invoice_no = data.get('invoice_no', '')

    if not phone or points <= 0:
        return jsonify({'success': False, 'message': 'Invalid phone or points requested'}), 400

    conn = get_db()
    cursor = conn.cursor()

    # Get customer name
    cursor.execute('SELECT name FROM customers WHERE phone = ?', (phone,))
    crow = cursor.fetchone()
    customer_name = crow['name'] if crow else f"Customer {phone[-4:]}"

    # Get firm details
    cursor.execute('SELECT * FROM firms WHERE id = ?', (firm_id,))
    frow = cursor.fetchone()
    if not frow:
        conn.close()
        return jsonify({'success': False, 'message': 'Firm not found'}), 404
    firm = dict(frow)

    # Check available points
    cursor.execute('''
    SELECT COALESCE(SUM(points_remaining), 0)
    FROM reward_batches
    WHERE customer_phone = ? AND status = 'ACTIVE' AND points_remaining > 0
    ''', (phone,))
    avail = float(cursor.fetchone()[0] or 0)

    if points > avail + 0.01:
        conn.close()
        return jsonify({'success': False, 'message': f"Insufficient active points ({avail:.2f} available)"}), 400

    # Calculate required bill (10x rule for ES PRO)
    multiplier = firm.get('min_purchase_multiplier', 10.0)
    required_bill = round(points * multiplier, 2) if multiplier > 1.0 else firm.get('min_bill_amount', 0.0)

    claim_id = f"CLAIM-{int(time.time())}-{random.randint(100, 999)}"
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Cancel previous pending claims for same phone and firm
    cursor.execute("UPDATE pending_redemption_claims SET status = 'CANCELLED' WHERE customer_phone = ? AND firm_id = ? AND status = 'PENDING'", (phone, firm_id))

    cursor.execute('''
    INSERT INTO pending_redemption_claims (id, customer_phone, customer_name, firm_id, points, batch_id, batch_invoice_no, required_bill, status, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)
    ''', (claim_id, phone, customer_name, firm_id, points, batch_id, invoice_no, required_bill, now_str))

    conn.commit()
    conn.close()

    claim_data = {
        'id': claim_id,
        'customer_phone': phone,
        'customer_name': customer_name,
        'firm_id': firm_id,
        'firm_name': firm['name'],
        'points': points,
        'batch_id': batch_id,
        'batch_invoice_no': invoice_no,
        'required_bill': required_bill,
        'created_at': now_str
    }

    # Broadcast event for live listeners
    event_payload = {
        'type': 'REDEMPTION_CLAIM_CREATED',
        'claim': claim_data,
        'phone': phone,
        'points': points,
        'firm_id': firm_id,
        'firm_name': firm['name'],
        'timestamp': time.time()
    }
    recent_sync_events.append(event_payload)
    if len(recent_sync_events) > MAX_EVENT_HISTORY:
        recent_sync_events.pop(0)

    return jsonify({
        'success': True,
        'message': f"Redemption claim for ₹{points:.2f} sent to {firm['name']} billing counter!",
        'claim': claim_data
    })

@app.route('/api/redemption/active-claims', methods=['GET'])
def get_active_redemption_claims():
    """
    Returns pending redemption claims for a firm and/or customer phone.
    Queried by EEYES Pro billing desk to pop up the discount prompt!
    """
    firm_id = request.args.get('firm_id')
    phone = request.args.get('phone')

    conn = get_db()
    cursor = conn.cursor()

    query = "SELECT * FROM pending_redemption_claims WHERE status = 'PENDING'"
    params = []

    if firm_id:
        query += " AND firm_id = ?"
        params.append(firm_id)
    if phone:
        clean_phone = phone.replace('+91', '').replace(' ', '').replace('-', '')
        query += " AND customer_phone = ?"
        params.append(clean_phone)

    query += " ORDER BY created_at DESC"
    cursor.execute(query, tuple(params))
    claims = [dict(r) for r in cursor.fetchall()]
    conn.close()

    return jsonify({'success': True, 'claims': claims})

# ----------------- MERCHANT-INITIATED REDEMPTION APPROVAL FLOW ----------------- #

@app.route('/api/redemption/merchant-request', methods=['POST'])
def create_merchant_redemption_request():
    """
    Called by EEYES Pro Cashier Counter:
    Cashier types/selects reward points to redeem and clicks "Send Request to Customer".
    Creates a pending authorization request and instantly notifies the customer in OmniPoints.
    """
    data = request.json or {}
    phone = str(data.get('phone', '')).strip().replace('+91', '').replace(' ', '').replace('-', '')
    firm_id = data.get('firm_id', 'firm-es-pro')
    points = float(data.get('points', 0))
    invoice_no = str(data.get('invoice_no', 'INV-DRAFT'))
    bill_amount = float(data.get('bill_amount', 0))

    if not phone or points <= 0:
        return jsonify({'success': False, 'message': 'Invalid customer phone or points amount'}), 400

    conn = get_db()
    try:
        cursor = conn.cursor()

        # Get customer name
        cursor.execute('SELECT name FROM customers WHERE phone = ?', (phone,))
        c_row = cursor.fetchone()
        customer_name = c_row['name'] if c_row else f"Customer {phone[-4:]}"

        # Get firm details
        cursor.execute('SELECT name FROM firms WHERE id = ?', (firm_id,))
        f_row = cursor.fetchone()
        firm_name = f_row['name'] if f_row else 'EEYES Pro Retail & Supermarket'

        req_id = f"REQ-M-{int(time.time())}-{random.randint(100, 999)}"
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Cancel previous pending requests for this phone and firm
        cursor.execute("UPDATE merchant_redemption_requests SET status = 'CANCELLED', updated_at = ? WHERE phone = ? AND firm_id = ? AND status = 'PENDING'", (now_str, phone, firm_id))

        cursor.execute('''
        INSERT INTO merchant_redemption_requests (id, phone, customer_name, firm_id, firm_name, invoice_no, points, bill_amount, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?, ?)
        ''', (req_id, phone, customer_name, firm_id, firm_name, invoice_no, points, bill_amount, now_str, now_str))
        conn.commit()
    finally:
        conn.close()

    # Broadcast notification to OmniPoints client
    publish_sync_event({
        'type': 'MERCHANT_REDEMPTION_REQUEST',
        'request_id': req_id,
        'phone': phone,
        'customer_name': customer_name,
        'firm_id': firm_id,
        'firm_name': firm_name,
        'invoice_no': invoice_no,
        'points': points,
        'bill_amount': bill_amount,
        'created_at': now_str
    })

    return jsonify({
        'success': True,
        'request_id': req_id,
        'phone': phone,
        'customer_name': customer_name,
        'points': points,
        'firm_name': firm_name,
        'message': f"Redemption request for ₹{points:.2f} successfully sent to customer's OmniPoints app"
    })

@app.route('/api/redemption/pending-merchant-request', methods=['GET'])
def get_pending_merchant_request():
    """
    Checks if there is an active pending merchant redemption request for the customer phone.
    """
    phone = str(request.args.get('phone', '')).strip().replace('+91', '').replace(' ', '').replace('-', '')
    if not phone:
        return jsonify({'success': False, 'message': 'Phone required'}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
    SELECT * FROM merchant_redemption_requests
    WHERE phone = ? AND status = 'PENDING'
    ORDER BY created_at DESC LIMIT 1
    ''', (phone,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return jsonify({'success': True, 'has_pending': False, 'request': None})

    return jsonify({
        'success': True,
        'has_pending': True,
        'request': dict(row)
    })

@app.route('/api/redemption/customer-response', methods=['POST'])
def respond_merchant_redemption_request():
    """
    Customer taps 'Accept & Deduct' or 'Decline' in OmniPoints.
    """
    data = request.json or {}
    request_id = data.get('request_id')
    action = str(data.get('action', '')).upper()

    if not request_id or action not in ['ACCEPT', 'DECLINE']:
        return jsonify({'success': False, 'message': 'Invalid parameters'}), 400

    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM merchant_redemption_requests WHERE id = ?', (request_id,))
        req_row = cursor.fetchone()
        if not req_row:
            return jsonify({'success': False, 'message': 'Request not found'}), 404

        req = dict(req_row)
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        new_status = 'ACCEPTED' if action == 'ACCEPT' else 'DECLINED'

        cursor.execute('''
        UPDATE merchant_redemption_requests
        SET status = ?, updated_at = ?
        WHERE id = ?
        ''', (new_status, now_str, request_id))
        conn.commit()
    finally:
        conn.close()

    # Publish sync event for EEYES Pro
    publish_sync_event({
        'type': 'MERCHANT_REQUEST_RESPONSE',
        'request_id': request_id,
        'status': new_status,
        'action': action,
        'phone': req['phone'],
        'points': req['points'],
        'invoice_no': req['invoice_no'],
        'firm_id': req['firm_id']
    })

    return jsonify({
        'success': True,
        'request_id': request_id,
        'status': new_status,
        'points': req['points'],
        'message': 'Redemption request accepted' if action == 'ACCEPT' else 'Redemption request declined'
    })

@app.route('/api/redemption/merchant-request-status/<req_id>', methods=['GET'])
def get_merchant_request_status(req_id):
    """
    Returns live status of a merchant redemption request (PENDING, ACCEPTED, DECLINED, COMPLETED, CANCELLED).
    """
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM merchant_redemption_requests WHERE id = ?', (req_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return jsonify({'success': False, 'message': 'Not found'}), 404
    return jsonify({'success': True, 'request': dict(row)})

@app.route('/api/redemption/merchant-request-cancel', methods=['POST'])
def cancel_merchant_redemption_request():
    """
    Cashier cancels the pending redemption request.
    """
    data = request.json or {}
    req_id = data.get('request_id')
    if not req_id:
        return jsonify({'success': False, 'message': 'Request ID required'}), 400

    conn = get_db()
    cursor = conn.cursor()
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute("UPDATE merchant_redemption_requests SET status = 'CANCELLED', updated_at = ? WHERE id = ? AND status = 'PENDING'", (now_str, req_id))
    conn.commit()
    conn.close()

    publish_sync_event({
        'type': 'MERCHANT_REQUEST_CANCELLED',
        'request_id': req_id
    })

    return jsonify({'success': True, 'message': 'Request cancelled'})

@app.route('/api/v1/erp/confirm-redemption', methods=['POST'])
def erp_confirm_redemption():
    """
    Executed when the Cashier applies/redeems the discount in the ERP invoice window.
    Deducts reward points from the customer's wallet in FIFO order, marks batch REDEEMED,
    records a transaction in the passbook, and pushes live updates to the web app!
    """
    data = request.json or {}
    phone = str(data.get('phone', '')).strip().replace('+91', '').replace(' ', '').replace('-', '')
    firm_id = data.get('firm_id', 'firm-es-pro')
    invoice_no = data.get('invoice_no', f"INV-{int(time.time())}")
    bill_amount = float(data.get('bill_amount', 0))
    discount_amount = float(data.get('discount_amount', 0))
    claim_id = data.get('claim_id')
    batch_ids = data.get('batch_ids') or []

    if not phone or discount_amount <= 0:
        return jsonify({'success': False, 'message': 'Valid phone and discount amount required'}), 400

    conn = get_db()
    try:
        cursor = conn.cursor()
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Get customer name
        cursor.execute('SELECT name FROM customers WHERE phone = ?', (phone,))
        crow = cursor.fetchone()
        customer_name = crow['name'] if crow else f"Customer {phone[-4:]}"

        # Get firm name
        cursor.execute('SELECT name FROM firms WHERE id = ?', (firm_id,))
        frow = cursor.fetchone()
        firm_name = frow['name'] if frow else 'Partner Store'

        # Deduct points from active batches using FIFO
        cursor.execute('''
        SELECT * FROM reward_batches
        WHERE customer_phone = ? AND status = 'ACTIVE' AND points_remaining > 0
        ORDER BY expiry_date ASC
        ''', (phone,))
        active_batches = [dict(r) for r in cursor.fetchall()]

        needed = discount_amount
        batches_affected = []

        for batch in active_batches:
            if needed <= 0:
                break
            avail_in_batch = batch['points_remaining']
            deduct_from_b = min(needed, avail_in_batch)
            new_rem = round(avail_in_batch - deduct_from_b, 2)
            new_status = 'REDEEMED' if new_rem <= 0.001 else 'ACTIVE'

            cursor.execute('''
            UPDATE reward_batches
            SET points_remaining = ?, status = ?
            WHERE id = ?
            ''', (new_rem, new_status, batch['id']))

            batches_affected.append({
                'batch_id': batch['id'],
                'invoice_no': batch['invoice_no'],
                'deducted': deduct_from_b,
                'remaining': new_rem
            })
            needed = round(needed - deduct_from_b, 2)

        # Record DEBIT / REDEEM transaction in passbook ledger
        tx_id = f"TX-RED-{int(time.time())}-{random.randint(100, 999)}"
        cursor.execute('''
        INSERT INTO transactions (id, customer_phone, firm_id, type, points, amount_equivalent,
                                 bill_no, bill_amount, description, batch_ids, created_at)
        VALUES (?, ?, ?, 'REDEEM', ?, ?, ?, ?, ?, ?, ?)
        ''', (
            tx_id,
            phone,
            firm_id,
            -discount_amount,
            -discount_amount,
            invoice_no,
            bill_amount,
            f"Redeemed ₹{discount_amount:.2f} on {firm_name} Invoice #{invoice_no}",
            json.dumps([b['batch_id'] for b in batches_affected]),
            now_str
        ))

        # Mark pending claim as COMPLETED
        if claim_id:
            cursor.execute("UPDATE pending_redemption_claims SET status = 'COMPLETED' WHERE id = ?", (claim_id,))
        else:
            cursor.execute("UPDATE pending_redemption_claims SET status = 'COMPLETED' WHERE customer_phone = ? AND firm_id = ? AND status = 'PENDING'", (phone, firm_id))

        # Mark merchant redemption request as COMPLETED
        merchant_request_id = data.get('merchant_request_id')
        if merchant_request_id:
            cursor.execute("UPDATE merchant_redemption_requests SET status = 'COMPLETED', updated_at = ? WHERE id = ?", (now_str, merchant_request_id))
        else:
            cursor.execute("UPDATE merchant_redemption_requests SET status = 'COMPLETED', updated_at = ? WHERE phone = ? AND firm_id = ? AND status = 'ACCEPTED'", (now_str, phone, firm_id))

        conn.commit()
    finally:
        conn.close()

    summary = calculate_customer_summary(phone)

    # Broadcast live event for mobile and web apps
    event_payload = {
        'type': 'WALLET_UPDATED',
        'action': 'REDEEMED',
        'phone': phone,
        'customer_name': customer_name,
        'points_deducted': discount_amount,
        'invoice_no': invoice_no,
        'firm_name': firm_name,
        'new_balance': summary['total_active_points'],
        'timestamp': time.time()
    }
    publish_sync_event(event_payload)

    return jsonify({
        'success': True,
        'message': f"₹{discount_amount:.2f} discount successfully applied to Invoice #{invoice_no} and deducted from {customer_name}'s wallet!",
        'customer_name': customer_name,
        'points_deducted': discount_amount,
        'new_balance': summary['total_active_points'],
        'invoice_no': invoice_no,
        'batches_affected': batches_affected
    })

# ----------------- GAMIFICATION / SCRATCH CARDS ----------------- #

@app.route('/api/gamification/scratch', methods=['POST'])
def scratch_card():
    data = request.json or {}
    card_id = data.get('card_id')
    phone = data.get('phone')

    if not card_id or not phone:
        return jsonify({'success': False, 'message': 'Missing card_id or phone'}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM scratch_cards WHERE id = ? AND customer_phone = ?', (card_id, phone))
    card = cursor.fetchone()

    if not card:
        conn.close()
        return jsonify({'success': False, 'message': 'Card not found'}), 404

    card = dict(card)
    if card['is_scratched']:
        conn.close()
        return jsonify({'success': False, 'message': 'Card has already been scratched', 'points': card['points_reward']})

    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    expiry_str = (datetime.now() + timedelta(days=14)).strftime('%Y-%m-%d 23:59:59')
    points = card['points_reward']

    # Mark card as scratched
    cursor.execute('UPDATE scratch_cards SET is_scratched = 1, scratched_at = ? WHERE id = ?', (now_str, card_id))

    # Add points as an active batch under ES PRO
    batch_id = f"BATCH-BONUS-{uuid.uuid4().hex[:8]}"
    cursor.execute('''
    INSERT INTO reward_batches (id, customer_phone, firm_id, invoice_no, bill_amount,
                                points_earned, points_remaining, earned_date, expiry_date,
                                required_bill_to_redeem, status, created_at)
    VALUES (?, ?, 'firm-es-pro', ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?)
    ''', (
        batch_id,
        phone,
        f"GIFT-{card_id}",
        0.00,
        points,
        points,
        now_str,
        expiry_str,
        points * 2.0, # Gentle unlock rule for bonus
        now_str
    ))

    # Add transaction record
    tx_id = f"TX-BONUS-{uuid.uuid4().hex[:8]}"
    cursor.execute('''
    INSERT INTO transactions (id, customer_phone, firm_id, type, points, amount_equivalent,
                             bill_no, bill_amount, description, batch_ids, created_at)
    VALUES (?, ?, 'firm-es-pro', 'BONUS', ?, ?, ?, 0.00, ?, ?, ?)
    ''', (
        tx_id,
        phone,
        points,
        points,
        f"SCRATCH-{card_id}",
        f"Won ₹{points:.2f} Bonus Reward Points from Mystery Scratch Card!",
        batch_id,
        now_str
    ))

    conn.commit()
    conn.close()

    summary = calculate_customer_summary(phone)
    return jsonify({
        'success': True,
        'message': f"Congratulations! You won ₹{points:.2f} Points!",
        'points_won': points,
        'summary': summary
    })

# ----------------- UNIVERSAL ERP & ES PRO INTEGRATION APIS ----------------- #

@app.route('/api/v1/erp/issue-reward', methods=['POST'])
def erp_issue_reward():
    """
    Standardized REST API called by ES PRO ERP or any connected firm when a customer makes a purchase.
    Calculates profit cashback / reward points and creates a new batch in customer's centralized wallet.
    """
    data = request.json or {}
    firm_id = data.get('firm_id', 'firm-es-pro')
    phone = str(data.get('customer_phone', '')).strip().replace('+91', '').replace(' ', '').replace('-', '')
    customer_name = data.get('customer_name', f"Customer {phone[-4:] if len(phone)>=4 else 'User'}")
    invoice_no = data.get('invoice_no', f"INV-{int(time.time())}")
    bill_amount = float(data.get('bill_amount', 0))
    profit_amount = float(data.get('profit_amount', 0))
    reward_points_override = data.get('reward_points') # Direct points if calculated by ERP
    payment_mode = str(data.get('payment_mode', 'cash')).lower() # cash, upi, bank, card, credit

    if not phone or len(phone) < 10 or bill_amount <= 0:
        return jsonify({'success': False, 'message': 'Valid 10-digit phone and bill amount required'}), 400

    conn = get_db()
    try:
        cursor = conn.cursor()

        # Verify firm
        cursor.execute('SELECT * FROM firms WHERE id = ?', (firm_id,))
        firm = cursor.fetchone()
        if not firm:
            return jsonify({'success': False, 'message': f'Firm ID {firm_id} not registered'}), 404
        firm = dict(firm)

        now = datetime.now()
        now_str = now.strftime('%Y-%m-%d %H:%M:%S')

        # Ensure customer exists or auto-register
        cursor.execute('SELECT * FROM customers WHERE phone = ?', (phone,))
        cust = cursor.fetchone()
        if not cust:
            cursor.execute('''
            INSERT INTO customers (phone, name, email, avatar_color, vip_tier, created_at)
            VALUES (?, ?, ?, '#4F46E5', 'Silver', ?)
            ''', (phone, customer_name, f"{phone}@rewards.espro", now_str))

        # Calculate points
        if reward_points_override is not None:
            points = float(reward_points_override)
        else:
            # ES PRO Standard Rule: 50% Profit Share Cashback on Ready Payments
            if payment_mode in ['credit', 'udhaar']:
                points = 0.0 # Ready payment required
            elif profit_amount > 0:
                points = profit_amount * 0.50 # 50% profit share
            else:
                # Fallback: 5% of bill amount
                points = bill_amount * 0.05

        if points <= 0:
            conn.commit()
            return jsonify({
                'success': True,
                'message': 'Bill recorded, but 0 reward points earned (Credit sale or no profit margin).',
                'points_issued': 0
            })

        points = round(points, 2)
        validity_days = firm['validity_days']
        expiry_date = (now + timedelta(days=validity_days)).strftime('%Y-%m-%d 23:59:59')
        
        # Calculate required bill to redeem (10x rule for ES PRO)
        multiplier = firm['min_purchase_multiplier']
        required_bill = round(points * multiplier, 2) if multiplier > 1.0 else firm['min_bill_amount']

        batch_id = f"BATCH-{firm_id[:6].upper()}-{uuid.uuid4().hex[:8]}"
        cursor.execute('''
        INSERT INTO reward_batches (id, customer_phone, firm_id, invoice_no, bill_amount,
                                    points_earned, points_remaining, earned_date, expiry_date,
                                    required_bill_to_redeem, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?)
        ''', (
            batch_id,
            phone,
            firm_id,
            invoice_no,
            bill_amount,
            points,
            points,
            now_str,
            expiry_date,
            required_bill,
            now_str
        ))

        # Transaction ledger entry
        tx_id = f"TX-ERP-{uuid.uuid4().hex[:8]}"
        cursor.execute('''
        INSERT INTO transactions (id, customer_phone, firm_id, type, points, amount_equivalent,
                                 bill_no, bill_amount, description, batch_ids, created_at)
        VALUES (?, ?, ?, 'EARN', ?, ?, ?, ?, ?, ?, ?)
        ''', (
            tx_id,
            phone,
            firm_id,
            points,
            points,
            invoice_no,
            bill_amount,
            f"Reward Points earned from Invoice #{invoice_no} at {firm['name']}",
            batch_id,
            now_str
        ))

        # Also log into firm_invoices ledger for gross purchases tracking
        cursor.execute('''
        INSERT OR REPLACE INTO firm_invoices (id, customer_phone, firm_id, invoice_type, invoice_no, amount, items_count, payment_mode, points_affected, notes, invoice_date, created_at)
        VALUES (?, ?, ?, 'PURCHASE', ?, ?, 1, ?, ?, ?, ?, ?)
        ''', (
            invoice_no,
            phone,
            firm_id,
            invoice_no,
            bill_amount,
            payment_mode.upper(),
            points,
            f"Invoice billing via {payment_mode.upper()} at {firm['name']}",
            now_str,
            now_str
        ))

        conn.commit()
    finally:
        conn.close()

    summary = calculate_customer_summary(phone)

    return jsonify({
        'success': True,
        'message': f"Issued ₹{points:.2f} points to customer {phone}!",
        'batch_id': batch_id,
        'points_issued': points,
        'expiry_date': expiry_date,
        'required_next_bill': required_bill,
        'total_active_wallet_points': summary['total_active_points']
    })

@app.route('/api/v1/erp/customer/register', methods=['POST'])
def erp_register_customer():
    """
    Standardized API called by EEYES PRO ERP to register a customer into OmniPoints.
    Returns the customer's Centralized Registered ID, Barcode, and Digital ID Pass.
    """
    data = request.json or {}
    phone = str(data.get('phone', '')).strip().replace('+91', '').replace(' ', '').replace('-', '')
    name = data.get('name', '').strip()
    email = data.get('email', f"{phone}@rewards.espro").strip()
    address = data.get('address', '')
    vip_tier = data.get('vip_tier', 'Silver')
    initial_bonus = float(data.get('initial_bonus', 50.0))
    source_firm = data.get('source_firm', 'firm-es-pro')

    if not phone or len(phone) < 10:
        return jsonify({'success': False, 'message': 'Valid 10-digit customer mobile number is required'}), 400

    if not name:
        name = f"Customer {phone[-4:]}"

    conn = get_db()
    try:
        cursor = conn.cursor()

        now = datetime.now()
        now_str = now.strftime('%Y-%m-%d %H:%M:%S')

        cursor.execute('SELECT * FROM customers WHERE phone = ?', (phone,))
        existing = cursor.fetchone()

        avatar_colors = ['#4F46E5', '#059669', '#EA580C', '#2563EB', '#DB2777', '#7C3AED']
        color = random.choice(avatar_colors)

        is_new = False
        if existing:
            # Update customer profile
            cursor.execute('''
            UPDATE customers
            SET name = ?, email = COALESCE(NULLIF(?, ''), email), vip_tier = ?
            WHERE phone = ?
            ''', (name, email, vip_tier, phone))
        else:
            is_new = True
            cursor.execute('''
            INSERT INTO customers (phone, name, email, avatar_color, vip_tier, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ''', (phone, name, email, color, vip_tier, now_str))

            # Award welcome bonus scratch card
            cursor.execute('''
            INSERT INTO scratch_cards (id, customer_phone, title, points_reward, is_scratched, created_at)
            VALUES (?, ?, '🎁 EEYES PRO Welcome Gift Card', ?, 0, ?)
            ''', (f"SC-WELCOME-{uuid.uuid4().hex[:8]}", phone, initial_bonus, now_str))

            # Also credit initial welcome batch if bonus > 0
            if initial_bonus > 0:
                batch_id = f"BATCH-WELCOME-{uuid.uuid4().hex[:8]}"
                expiry_date = (now + timedelta(days=14)).strftime('%Y-%m-%d 23:59:59')
                cursor.execute('''
                INSERT INTO reward_batches (id, customer_phone, firm_id, invoice_no, bill_amount,
                                            points_earned, points_remaining, earned_date, expiry_date,
                                            required_bill_to_redeem, status, created_at)
                VALUES (?, ?, ?, 'REG-BONUS', 0.0, ?, ?, ?, ?, ?, 'ACTIVE', ?)
                ''', (
                    batch_id, phone, source_firm, initial_bonus, initial_bonus,
                    now_str, expiry_date, initial_bonus * 2.0, now_str
                ))

                tx_id = f"TX-REG-{uuid.uuid4().hex[:8]}"
                cursor.execute('''
                INSERT INTO transactions (id, customer_phone, firm_id, type, points, amount_equivalent,
                                         bill_no, bill_amount, description, batch_ids, created_at)
                VALUES (?, ?, ?, 'BONUS', ?, ?, 'REG-BONUS', 0.0,
                        'EEYES PRO Registration Bonus Points Added', ?, ?)
                ''', (tx_id, phone, source_firm, initial_bonus, initial_bonus, batch_id, now_str))

        conn.commit()

        # Retrieve updated customer
        cursor.execute('SELECT * FROM customers WHERE phone = ?', (phone,))
        customer = dict(cursor.fetchone())
    finally:
        conn.close()

    summary = calculate_customer_summary(phone)
    registered_id = f"EEYES-OP-{phone}"

    return jsonify({
        'success': True,
        'message': f"{'Registered new' if is_new else 'Updated'} customer {name} in OmniPoints Network!",
        'is_new_customer': is_new,
        'customer': {
            'registered_id': registered_id,
            'phone': phone,
            'name': name,
            'email': email,
            'vip_tier': customer.get('vip_tier', 'Silver'),
            'avatar_color': customer.get('avatar_color', color),
            'barcode': f"OP{phone}",
            'qr_data': f"OMNIPOINTS:CUSTOMER:{registered_id}:PHONE:{phone}",
            'id_card_url': f"http://127.0.0.1:5050/?phone={phone}&view=id-card",
            'registered_date': customer.get('created_at', now_str).split(' ')[0]
        },
        'wallet': summary
    })

@app.route('/api/v1/erp/customer/<phone>', methods=['GET'])
def erp_get_customer(phone):
    """Returns customer's registered identity, wallet balance and batches for EEYES PRO POS"""
    phone = str(phone).strip().replace('+91', '').replace(' ', '').replace('-', '')
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM customers WHERE phone = ?', (phone,))
    customer = cursor.fetchone()
    if not customer:
        conn.close()
        return jsonify({
            'success': False,
            'registered': False,
            'message': f'Customer {phone} is not yet registered in OmniPoints'
        }), 404

    customer_dict = dict(customer)
    conn.close()

    summary = calculate_customer_summary(phone)
    ledger = get_customer_business_ledger(phone)
    registered_id = f"EEYES-OP-{phone}"

    # Fetch store profiles
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
    SELECT p.firm_id, f.name as firm_name, p.registered_name, p.account_no
    FROM firm_customer_profiles p
    JOIN firms f ON p.firm_id = f.id
    WHERE p.customer_phone = ?
    ''', (phone,))
    firm_profiles = [dict(r) for r in cursor.fetchall()]
    conn.close()

    return jsonify({
        'success': True,
        'registered': True,
        'customer': {
            'registered_id': registered_id,
            'phone': phone,
            'name': customer_dict['name'],
            'email': customer_dict['email'],
            'vip_tier': customer_dict['vip_tier'],
            'avatar_color': customer_dict['avatar_color'],
            'barcode': f"OP{phone}",
            'qr_data': f"OMNIPOINTS:CUSTOMER:{registered_id}:PHONE:{phone}",
            'id_card_url': f"http://127.0.0.1:5050/?phone={phone}&view=id-card",
            'registered_date': customer_dict['created_at'].split(' ')[0],
            'firm_profiles': firm_profiles
        },
        'wallet': summary,
        'business_ledger': ledger
    })

@app.route('/api/v1/erp/firm-rules', methods=['GET'])
def erp_firm_rules():
    """Returns rule configurations for all firms for ERP synchronization"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, category, min_purchase_multiplier, min_bill_amount, max_redemption_pct, max_points_per_txn, validity_days, next_day_redemption_only, rule_summary FROM firms')
    rules = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({'success': True, 'firm_rules': rules})

# ----------------- EEYES PRO DESKTOP ERP LIVE SYNCHRONIZER ----------------- #

def sync_from_eeyes_pro():
    """
    Directly pulls full state (Parties, Invoices, Returns) from EEYES PRO Desktop Web App
    (via local files in vyapar-web/data or fallback to http://127.0.0.1:3000/api/sync/full-state).
    Registers customers, imports sales invoices with 50% profit share rewards,
    imports sale returns into firm_invoices and ledger.
    """
    import json

    state = {'parties': [], 'invoices': [], 'returns': []}
    data_dir = r"C:\Users\LENOVO\.gemini\antigravity\scratch\vyapar-web\data"
    p_file = os.path.join(data_dir, "eeyes-parties.json")
    i_file = os.path.join(data_dir, "eeyes-invoices.json")
    r_file = os.path.join(data_dir, "eeyes-returns.json")

    # 1. Read directly from EEYES Pro data files (instant <1ms)
    if os.path.exists(p_file):
        try:
            with open(p_file, 'r', encoding='utf-8') as f:
                state['parties'] = json.load(f)
        except Exception: pass
    if os.path.exists(i_file):
        try:
            with open(i_file, 'r', encoding='utf-8') as f:
                state['invoices'] = json.load(f)
        except Exception: pass
    if os.path.exists(r_file):
        try:
            with open(r_file, 'r', encoding='utf-8') as f:
                state['returns'] = json.load(f)
        except Exception: pass

    parties = state.get('parties', [])
    invoices = state.get('invoices', [])
    returns = state.get('returns', [])

    conn = get_db()
    conn.isolation_level = None
    cursor = conn.cursor()
    now = datetime.now()
    now_str = now.strftime('%Y-%m-%d %H:%M:%S')

    synced_customers = 0
    synced_sales = 0
    synced_returns = 0

    # Sync Customers
    for p in parties:
        phone = str(p.get('phone', '')).replace('+91', '').replace(' ', '').replace('-', '').strip()
        if len(phone) < 10:
            continue
        name = p.get('name', f"Customer {phone[-4:]}")
        email = p.get('email', f"{phone}@eeyespro.in")

        # Check existing
        cursor.execute('SELECT * FROM customers WHERE phone = ?', (phone,))
        existing_cust = cursor.fetchone()
        if not existing_cust:
            cursor.execute('''
            INSERT INTO customers (phone, name, email, avatar_color, vip_tier, created_at)
            VALUES (?, ?, ?, '#E11D48', 'Gold VIP', ?)
            ''', (phone, name, email, now_str))
            # Welcome scratch card
            cursor.execute('''
            INSERT INTO scratch_cards (id, customer_phone, title, points_reward, is_scratched, created_at)
            VALUES (?, ?, '🎁 EEYES Pro Welcome Gift Bonus', 50.00, 0, ?)
            ''', (f"SC-EEYES-{phone}", phone, now_str))
        else:
            # Keep name up to date
            cursor.execute('UPDATE customers SET name = ? WHERE phone = ?', (name, phone))

        # Ensure firm profile in EEYES Pro store
        cursor.execute('''
        INSERT OR REPLACE INTO firm_customer_profiles (customer_phone, firm_id, registered_name, account_no, created_at)
        VALUES (?, 'firm-es-pro', ?, ?, ?)
        ''', (phone, name, f"EY-{phone[-4:]}", now_str))
        synced_customers += 1

    # Sync Sales Invoices
    for inv in invoices:
        phone = str(inv.get('partyPhone', inv.get('customer_phone', ''))).replace('+91', '').replace(' ', '').replace('-', '').strip()
        if len(phone) < 10:
            continue
        invoice_no = inv.get('invoiceNo')
        if not invoice_no:
            continue

        amount = float(inv.get('grandTotal', inv.get('bill_amount', 0)))
        profit = float(inv.get('invoiceProfit', inv.get('profit_amount', amount * 0.15)))
        points = float(inv.get('rewardAmount', inv.get('reward_points', profit * 0.5)))
        payment_mode = str(inv.get('paymentMode', 'Cash')).upper()
        date_str = inv.get('date', now.strftime('%Y-%m-%d'))
        items_count = int(inv.get('itemsCount', 1))
        notes = inv.get('notes', f"EEYES Pro Sale #{invoice_no}")

        # Check if invoice already recorded in firm_invoices
        cursor.execute('SELECT id FROM firm_invoices WHERE id = ?', (invoice_no,))
        if not cursor.fetchone():
            # 1. Insert into firm_invoices
            cursor.execute('''
            INSERT INTO firm_invoices (id, customer_phone, firm_id, invoice_type, invoice_no, amount, items_count, payment_mode, points_affected, notes, invoice_date, created_at)
            VALUES (?, ?, 'firm-es-pro', 'PURCHASE', ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (invoice_no, phone, invoice_no, amount, items_count, payment_mode, points, notes, date_str, now_str))

            # 2. Insert into transactions
            tx_id = f"TX-EEYES-{invoice_no}"
            batch_id = f"BATCH-EEYES-{invoice_no}"
            cursor.execute('''
            INSERT OR REPLACE INTO transactions (id, customer_phone, firm_id, type, points, amount_equivalent, bill_no, bill_amount, description, batch_ids, created_at)
            VALUES (?, ?, 'firm-es-pro', 'EARN', ?, ?, ?, ?, ?, ?, ?)
            ''', (tx_id, phone, points, points, invoice_no, amount, f"50% Profit Share Cashback from EEYES Pro Invoice #{invoice_no} ({notes})", batch_id, now_str))

            # 3. Insert into reward_batches (7-day validity, 10x rule)
            try:
                base_dt = datetime.strptime(date_str, '%Y-%m-%d')
            except Exception:
                base_dt = now
            expiry_dt = base_dt + timedelta(days=7)
            exp_str = expiry_dt.strftime('%Y-%m-%d 23:59:59')
            req_bill = round(points * 10.0, 2) # 10x purchase rule!

            cursor.execute('''
            INSERT OR REPLACE INTO reward_batches (id, customer_phone, firm_id, invoice_no, bill_amount, points_earned, points_remaining, earned_date, expiry_date, required_bill_to_redeem, status, created_at)
            VALUES (?, ?, 'firm-es-pro', ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?)
            ''', (batch_id, phone, invoice_no, amount, points, points, date_str, exp_str, req_bill, now_str))

            synced_sales += 1

    # Sync Returns
    for ret in returns:
        phone = str(ret.get('partyPhone', ret.get('phone', ''))).replace('+91', '').replace(' ', '').replace('-', '').strip()
        if len(phone) < 10:
            continue
        return_slip_no = ret.get('returnSlipNo', ret.get('return_slip_no'))
        if not return_slip_no:
            continue

        ret_amount = float(ret.get('returnAmount', ret.get('return_amount', 0)))
        orig_inv = ret.get('originalInvoiceNo', ret.get('original_invoice_no', ''))
        reason = ret.get('reason', 'EEYES Pro Sale Return / Goods Surrender')
        date_str = ret.get('date', now.strftime('%Y-%m-%d'))

        cursor.execute('SELECT id FROM firm_invoices WHERE id = ?', (return_slip_no,))
        if not cursor.fetchone():
            cursor.execute('''
            INSERT INTO firm_invoices (id, customer_phone, firm_id, invoice_type, invoice_no, amount, items_count, payment_mode, points_affected, notes, invoice_date, created_at)
            VALUES (?, ?, 'firm-es-pro', 'RETURN', ?, ?, 1, 'Credit Memo', 0.0, ?, ?, ?)
            ''', (return_slip_no, phone, return_slip_no, ret_amount, f"{reason} (Ref: {orig_inv})", date_str, now_str))

            tx_id = f"TX-EEYES-{return_slip_no}"
            cursor.execute('''
            INSERT OR REPLACE INTO transactions (id, customer_phone, firm_id, type, points, amount_equivalent, bill_no, bill_amount, description, batch_ids, created_at)
            VALUES (?, ?, 'firm-es-pro', 'RETURN', 0.0, ?, ?, ?, ?, '', ?)
            ''', (tx_id, phone, ret_amount, return_slip_no, ret_amount, f"Surrender / Goods Return Slip #{return_slip_no} at EEYES Pro Store (₹{ret_amount:.2f})", now_str))

            synced_returns += 1

    conn.commit()
    conn.close()

    return {
        'success': True,
        'message': f"Synced {synced_customers} Customers, {synced_sales} Sales Invoices, and {synced_returns} Sale Returns from EEYES PRO Desktop!",
        'synced_customers': synced_customers,
        'synced_sales': synced_sales,
        'synced_returns': synced_returns
    }

@app.route('/api/v1/erp/sync-eeyes-pro', methods=['GET', 'POST'])
def erp_sync_eeyes_pro():
    result = sync_from_eeyes_pro()
    return jsonify(result)

# ----------------- REAL-TIME MULTI-DEVICE MIRROR & LIVE SYNC ENGINE ----------------- #

connected_sync_clients = set()
recent_sync_events = []
MAX_EVENT_HISTORY = 60

async def ws_sync_handler(websocket):
    connected_sync_clients.add(websocket)
    device_count = len(connected_sync_clients)
    print(f"[LiveSync] Device connected via WebSocket. Active Devices: {device_count}")

    try:
        # Acknowledge connection with device count
        await websocket.send(json.dumps({
            'type': 'SYNC_CONNECTED',
            'deviceCount': device_count,
            'timestamp': time.time()
        }))

        # Broadcast updated device count to all connected clients
        count_msg = json.dumps({'type': 'DEVICE_COUNT', 'deviceCount': device_count})
        for ws in list(connected_sync_clients):
            if ws != websocket:
                try:
                    await ws.send(count_msg)
                except Exception:
                    pass

        async for message in websocket:
            try:
                data = json.loads(message)
                data['serverTime'] = time.time()

                # Add to history for polling clients
                recent_sync_events.append(data)
                if len(recent_sync_events) > MAX_EVENT_HISTORY:
                    recent_sync_events.pop(0)

                # Broadcast to all OTHER connected devices in real time
                payload = json.dumps(data)
                dead_sockets = set()
                for ws in list(connected_sync_clients):
                    if ws != websocket:
                        try:
                            await ws.send(payload)
                        except Exception:
                            dead_sockets.add(ws)

                for dead in dead_sockets:
                    connected_sync_clients.discard(dead)
            except Exception as e:
                print(f"[LiveSync] Message error: {e}")
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        connected_sync_clients.discard(websocket)
        device_count = len(connected_sync_clients)
        print(f"[LiveSync] Device disconnected. Active Devices: {device_count}")
        count_msg = json.dumps({'type': 'DEVICE_COUNT', 'deviceCount': device_count})
        for ws in list(connected_sync_clients):
            try:
                await ws.send(count_msg)
            except Exception:
                pass

ws_event_loop = None

def publish_sync_event(event_dict):
    global ws_event_loop
    event_dict['serverTime'] = time.time()
    recent_sync_events.append(event_dict)
    if len(recent_sync_events) > MAX_EVENT_HISTORY:
        recent_sync_events.pop(0)
    if ws_event_loop and connected_sync_clients:
        try:
            msg = json.dumps(event_dict)
            for ws in list(connected_sync_clients):
                try:
                    asyncio.run_coroutine_threadsafe(ws.send(msg), ws_event_loop)
                except Exception:
                    pass
        except Exception:
            pass

def start_live_sync_ws_server():
    global ws_event_loop
    async def main():
        async with websockets.serve(ws_sync_handler, "0.0.0.0", 5051):
            print("OmniPoints Live Sync WebSocket Server running on ws://0.0.0.0:5051")
            await asyncio.Future()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    ws_event_loop = loop
    try:
        loop.run_until_complete(main())
    except Exception as e:
        print(f"[LiveSync] WebSocket Server Error: {e}")

# Start background sync thread
sync_thread = threading.Thread(target=start_live_sync_ws_server, daemon=True)
sync_thread.start()

@app.route('/api/sync/broadcast', methods=['POST'])
def http_sync_broadcast():
    """HTTP fallback for broadcasting live sync events"""
    data = request.json or {}
    data['serverTime'] = time.time()
    recent_sync_events.append(data)
    if len(recent_sync_events) > MAX_EVENT_HISTORY:
        recent_sync_events.pop(0)
    return jsonify({'success': True, 'deviceCount': len(connected_sync_clients)})

@app.route('/api/sync/poll', methods=['GET'])
def http_sync_poll():
    """HTTP fallback for polling live sync events"""
    since = float(request.args.get('since', 0))
    events = [e for e in recent_sync_events if e.get('serverTime', 0) > since]
    return jsonify({'success': True, 'events': events, 'deviceCount': len(connected_sync_clients)})

# Auto-initialize database tables on import or direct run
init_db()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5050))
    print(f"OmniPoints Server running on port {port}...")
    app.run(host='0.0.0.0', port=port, debug=False)
