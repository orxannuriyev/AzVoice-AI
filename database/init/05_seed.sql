-- ============================================================
-- Test datası — 1 otel, 3 otaq tipi, 10 otaq, 30 günlük
-- availability, 5 xidmət, 1 kampaniya, 3 qonaq, 2 rezervasiya
-- ============================================================

INSERT INTO hotel_info (name, address, city, phone, timezone, check_in_time, check_out_time, currency)
VALUES ('Astana Hotel', 'Neftçilər prospekti 153', 'Bakı',
        '+994124980000', 'Asia/Baku', '14:00', '12:00', 'AZN');

-- Sabit UUID-lər (testlərdə istinad asan olsun deyə)
INSERT INTO room_types (id, name, description, base_price, max_occupancy, amenities) VALUES
('22222222-2222-2222-2222-222222222201',
 'Standart', 'Şəhər mənzərəli standart otaq', 120.00, 2,
 '["wifi","tv","kondisioner","mini-bar"]'),
('22222222-2222-2222-2222-222222222202',
 'Delüks', 'Dəniz mənzərəli geniş otaq', 200.00, 3,
 '["wifi","tv","kondisioner","mini-bar","balkon","dəniz mənzərəsi"]'),
('22222222-2222-2222-2222-222222222203',
 'Suit', 'İki otaqlı lüks süit', 350.00, 4,
 '["wifi","tv","kondisioner","mini-bar","balkon","jakuzi","qonaq otağı"]');

-- 10 otaq: 5 Stəndard, 3 Dilaks, 2 Svit
INSERT INTO rooms (room_type_id, room_number, floor) VALUES
('22222222-2222-2222-2222-222222222201', '101', 1),
('22222222-2222-2222-2222-222222222201', '102', 1),
('22222222-2222-2222-2222-222222222201', '103', 1),
('22222222-2222-2222-2222-222222222201', '201', 2),
('22222222-2222-2222-2222-222222222201', '202', 2),
('22222222-2222-2222-2222-222222222202', '301', 3),
('22222222-2222-2222-2222-222222222202', '302', 3),
('22222222-2222-2222-2222-222222222202', '303', 3),
('22222222-2222-2222-2222-222222222203', '401', 4),
('22222222-2222-2222-2222-222222222203', '402', 4);

-- Rate plan-lar (yay qiymətləri)
INSERT INTO rate_plans (room_type_id, name, price, valid_from, valid_to, conditions) VALUES
('22222222-2222-2222-2222-222222222201', 'Yay tarifi', 140.00, CURRENT_DATE, CURRENT_DATE + 60, '{"min_nights": 1}'),
('22222222-2222-2222-2222-222222222202', 'Yay tarifi', 230.00, CURRENT_DATE, CURRENT_DATE + 60, '{"min_nights": 1}'),
('22222222-2222-2222-2222-222222222203', 'Yay tarifi', 400.00, CURRENT_DATE, CURRENT_DATE + 60, '{"min_nights": 2}');

-- 365 günlük availability (bu gündən başlayaraq).
-- Qeyd: mövcud (köhnə seed-lə qurulmuş) bazalarda cədvəl qısa ola bilər —
-- tətbiq səviyyəsində _ensure_availability (src/db/hotel_tools.py)
-- çatışmayan günləri rezervasiya üfüqü daxilində avtomatik əlavə edir.
INSERT INTO availability (room_type_id, date, total_rooms)
SELECT rt.id, d::date, rt.cnt
FROM (VALUES
        ('22222222-2222-2222-2222-222222222201'::uuid, 5),
        ('22222222-2222-2222-2222-222222222202'::uuid, 3),
        ('22222222-2222-2222-2222-222222222203'::uuid, 2)
     ) AS rt(id, cnt)
CROSS JOIN generate_series(CURRENT_DATE, CURRENT_DATE + 365, '1 day') AS d;

-- 5 xidmət
INSERT INTO services (name, description, price, category) VALUES
('Spa paketi', '60 dəqiqəlik masaj və hamam', 80.00, 'spa'),
('Hava limanı transferi', 'Heydər Əliyev Hava Limanından/na transfer', 35.00, 'transfer'),
('Səhər yeməyi', 'Açıq bufet səhər yeməyi', 25.00, 'breakfast'),
('Camaşırxana', 'Gündəlik camaşır xidməti', 15.00, 'laundry'),
('Gecikmiş çek-aut', 'Saat 18:00-a qədər çek-aut', 40.00, 'other');

-- 1 aktiv kampaniya
INSERT INTO campaigns (name, discount_type, discount_value, valid_from, valid_to, conditions) VALUES
('Yay endirimi', 'percent', 15.00, CURRENT_DATE, CURRENT_DATE + 45,
 '{"min_nights": 3, "room_types": ["Delüks","Suit"]}');

-- 3 qonaq
INSERT INTO guests (id, full_name, phone, email, notes) VALUES
('33333333-3333-3333-3333-333333333301',
 'Rəşad Məmmədov', '+994501234567', 'reshad.m@example.com', 'Daimi qonaq, yuxarı mərtəbə üstünlük'),
('33333333-3333-3333-3333-333333333302',
 'Aygün Əliyeva', '+994552345678', 'aygun.a@example.com', NULL),
('33333333-3333-3333-3333-333333333303',
 'Elvin Hüseynov', '+994703456789', NULL, 'Səssiz otaq xahiş edib');

-- 2 rezervasiya (trigger booked_rooms-u avtomatik artıracaq)
INSERT INTO reservations (guest_id, room_type_id, check_in, check_out, status, total_price, call_id) VALUES
('33333333-3333-3333-3333-333333333301', '22222222-2222-2222-2222-222222222202',
 CURRENT_DATE + 3, CURRENT_DATE + 6, 'confirmed', 690.00, 'call_demo_001'),
('33333333-3333-3333-3333-333333333302', '22222222-2222-2222-2222-222222222201',
 CURRENT_DATE + 5, CURRENT_DATE + 7, 'pending', 280.00, 'call_demo_002');

-- Rezervasiya ödənişi
INSERT INTO payments (reservation_id, amount, status, method)
SELECT id, total_price, 'paid', 'card'
FROM reservations WHERE call_id = 'call_demo_001';

-- Staff
INSERT INTO staff (full_name, role, phone, email, permissions) VALUES
('Nigar Qasımova', 'manager', '+994124980001', 'nigar.q@astanahotel.az',
 '{"can_cancel": true, "can_refund": true}'),
('Tural İsmayılov', 'receptionist', '+994124980002', 'tural.i@astanahotel.az',
 '{"can_cancel": false, "can_refund": false}');

-- Knowledge base nümunələri (embedding NULL — ingestion pipeline dolduracaq)
INSERT INTO knowledge_base (content, category, source) VALUES
('Çek-in saat 14:00-dan başlayır, çek-aut saat 12:00-a qədərdir. Erkən çek-in mövcudluqdan asılıdır.',
 'policy', 'hotel_policy.md'),
('Rezervasiya çek-in tarixinə 48 saat qalana qədər pulsuz ləğv edilə bilər. Daha gec ləğvlərdə ilk gecənin qiyməti tutulur.',
 'policy', 'cancellation_policy.md'),
('Oteldə pulsuz Vay-Fay, açıq hovuz, fitnes zalı və spa mərkəzi mövcuddur. Hovuz 07:00-22:00 arası açıqdır.',
 'faq', 'faq.md');
