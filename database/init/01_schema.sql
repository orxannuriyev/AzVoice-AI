-- ============================================================
-- Hotel AI Call Center — Core schema (single hotel)
-- hotel_info: single-row table — the hotel's own data
-- ============================================================

-- ENUM types
CREATE TYPE room_status AS ENUM ('available', 'occupied', 'maintenance', 'cleaning');
CREATE TYPE reservation_status AS ENUM ('pending', 'confirmed', 'checked_in', 'checked_out', 'cancelled');
CREATE TYPE service_category AS ENUM ('spa', 'transfer', 'breakfast', 'laundry', 'other');
CREATE TYPE discount_type AS ENUM ('percent', 'fixed');
CREATE TYPE payment_status AS ENUM ('pending', 'paid', 'refunded');
CREATE TYPE kb_category AS ENUM ('policy', 'faq', 'service_desc', 'marketing');

-- 1. hotel_info (single row — the hotel's own data)
CREATE TABLE hotel_info (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name           varchar(255) NOT NULL,
    address        text,
    city           varchar(100),
    phone          varchar(30),
    timezone       varchar(50) NOT NULL DEFAULT 'Asia/Baku',
    check_in_time  time NOT NULL DEFAULT '14:00',
    check_out_time time NOT NULL DEFAULT '12:00',
    currency       char(3) NOT NULL DEFAULT 'AZN',
    is_active      boolean NOT NULL DEFAULT true,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now()
);

-- 2. room_types
CREATE TABLE room_types (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name          varchar(100) NOT NULL UNIQUE,
    description   text,
    base_price    numeric(10,2) NOT NULL CHECK (base_price >= 0),
    max_occupancy int NOT NULL CHECK (max_occupancy > 0),
    amenities     jsonb NOT NULL DEFAULT '[]'::jsonb,
    is_active     boolean NOT NULL DEFAULT true,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now()
);

-- 3. rooms
CREATE TABLE rooms (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    room_type_id uuid NOT NULL REFERENCES room_types(id) ON DELETE CASCADE,
    room_number  varchar(20) NOT NULL UNIQUE,
    floor        int,
    status       room_status NOT NULL DEFAULT 'available',
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now()
);

-- 4. rate_plans
CREATE TABLE rate_plans (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    room_type_id uuid NOT NULL REFERENCES room_types(id) ON DELETE CASCADE,
    name         varchar(100) NOT NULL,
    price        numeric(10,2) NOT NULL CHECK (price >= 0),
    valid_from   date NOT NULL,
    valid_to     date NOT NULL,
    conditions   jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    CHECK (valid_to >= valid_from)
);

-- 5. availability
CREATE TABLE availability (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    room_type_id uuid NOT NULL REFERENCES room_types(id) ON DELETE CASCADE,
    date         date NOT NULL,
    total_rooms  int NOT NULL CHECK (total_rooms >= 0),
    booked_rooms int NOT NULL DEFAULT 0 CHECK (booked_rooms >= 0),
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (room_type_id, date),
    CHECK (booked_rooms <= total_rooms)
);

-- 6. guests
CREATE TABLE guests (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    full_name  varchar(255) NOT NULL,
    phone      varchar(30) NOT NULL UNIQUE,
    email      varchar(255),
    notes      text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- 7. reservations
CREATE TABLE reservations (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    guest_id     uuid NOT NULL REFERENCES guests(id) ON DELETE RESTRICT,
    room_type_id uuid NOT NULL REFERENCES room_types(id) ON DELETE RESTRICT,
    room_id      uuid REFERENCES rooms(id) ON DELETE SET NULL,
    check_in     date NOT NULL,
    check_out    date NOT NULL,
    status       reservation_status NOT NULL DEFAULT 'pending',
    total_price  numeric(10,2) CHECK (total_price >= 0),
    short_code   varchar(6) UNIQUE,
    created_via  varchar(50) NOT NULL DEFAULT 'call_center',
    call_id      varchar(100),
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    CHECK (check_out > check_in)
);

-- 8. services
CREATE TABLE services (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name        varchar(100) NOT NULL,
    description text,
    price       numeric(10,2) NOT NULL CHECK (price >= 0),
    category    service_category NOT NULL DEFAULT 'other',
    is_active   boolean NOT NULL DEFAULT true,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

-- 9. campaigns
CREATE TABLE campaigns (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name           varchar(150) NOT NULL,
    discount_type  discount_type NOT NULL,
    discount_value numeric(10,2) NOT NULL CHECK (discount_value > 0),
    valid_from     date NOT NULL,
    valid_to       date NOT NULL,
    conditions     jsonb NOT NULL DEFAULT '{}'::jsonb,
    is_active      boolean NOT NULL DEFAULT true,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),
    CHECK (valid_to >= valid_from)
);

-- 10. payments
CREATE TABLE payments (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    reservation_id  uuid NOT NULL REFERENCES reservations(id) ON DELETE CASCADE,
    amount          numeric(10,2) NOT NULL CHECK (amount >= 0),
    status          payment_status NOT NULL DEFAULT 'pending',
    method          varchar(50),
    transaction_ref varchar(150),
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

-- 11. call_logs
CREATE TABLE call_logs (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    call_id          varchar(100) NOT NULL,
    phone_number     varchar(30),
    transcript       text,
    intent_detected  varchar(100),
    tool_calls       jsonb NOT NULL DEFAULT '[]'::jsonb,
    duration_seconds int,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now()
);

-- 12. knowledge_base (RAG)
CREATE TABLE knowledge_base (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    content    text NOT NULL,
    embedding  vector(1536),
    category   kb_category NOT NULL DEFAULT 'faq',
    source     varchar(255),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- 13. staff
CREATE TABLE staff (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    full_name   varchar(255) NOT NULL,
    role        varchar(50) NOT NULL,
    phone       varchar(30),
    email       varchar(255),
    permissions jsonb NOT NULL DEFAULT '{}'::jsonb,
    is_active   boolean NOT NULL DEFAULT true,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);
