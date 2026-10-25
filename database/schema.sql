-- Schéma PostgreSQL du catalogue produits TechSahel.
-- Idempotent : peut être rejoué sans erreur (CREATE ... IF NOT EXISTS).
-- Les images ne sont PAS stockées en base : seule une clé d'objet (image_key) l'est.

CREATE TABLE IF NOT EXISTS categories (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL UNIQUE,
    slug        VARCHAR(100) NOT NULL UNIQUE,
    description TEXT         NOT NULL DEFAULT '',
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT categories_slug_format CHECK (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$')
);

CREATE TABLE IF NOT EXISTS products (
    id           SERIAL PRIMARY KEY,
    category_id  INTEGER       NOT NULL REFERENCES categories (id) ON DELETE RESTRICT,
    name         VARCHAR(200)  NOT NULL,
    slug         VARCHAR(200)  NOT NULL UNIQUE,
    brand        VARCHAR(100)  NOT NULL DEFAULT '',
    description  TEXT          NOT NULL DEFAULT '',
    price_xof    INTEGER       NOT NULL,
    stock_status VARCHAR(20)   NOT NULL DEFAULT 'in_stock',
    image_key    VARCHAR(255),
    created_at   TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ   NOT NULL DEFAULT now(),
    CONSTRAINT products_price_positive CHECK (price_xof >= 0),
    CONSTRAINT products_stock_status_valid
        CHECK (stock_status IN ('in_stock', 'low_stock', 'out_of_stock', 'on_order')),
    CONSTRAINT products_slug_format CHECK (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$')
);

CREATE INDEX IF NOT EXISTS idx_products_category_id ON products (category_id);
CREATE INDEX IF NOT EXISTS idx_products_stock_status ON products (stock_status);
CREATE INDEX IF NOT EXISTS idx_products_price ON products (price_xof);

CREATE TABLE IF NOT EXISTS inquiries (
    id             SERIAL PRIMARY KEY,
    customer_name  VARCHAR(120) NOT NULL,
    customer_email VARCHAR(254) NOT NULL,
    customer_phone VARCHAR(30),
    product_id     INTEGER REFERENCES products (id) ON DELETE SET NULL,
    message        TEXT         NOT NULL,
    status         VARCHAR(20)  NOT NULL DEFAULT 'new',
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT inquiries_status_valid CHECK (status IN ('new', 'in_progress', 'closed')),
    CONSTRAINT inquiries_message_not_blank CHECK (length(btrim(message)) > 0),
    CONSTRAINT inquiries_name_not_blank CHECK (length(btrim(customer_name)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_inquiries_product_id ON inquiries (product_id);
CREATE INDEX IF NOT EXISTS idx_inquiries_status_created ON inquiries (status, created_at DESC);

-- Maintien automatique de products.updated_at.
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_products_updated_at ON products;
CREATE TRIGGER trg_products_updated_at
    BEFORE UPDATE ON products
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
