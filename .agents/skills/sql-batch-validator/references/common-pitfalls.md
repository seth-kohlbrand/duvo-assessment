# Common PostgreSQL/Supabase SQL Pitfalls

Quick reference for the errors you'll hit most often. Organized by frequency.

## Table Creation

### 1. Trailing comma before closing paren
```sql
-- ❌ WRONG
CREATE TABLE users (
  id UUID PRIMARY KEY,
  name TEXT,  -- ← trailing comma
);

-- ✅ CORRECT
CREATE TABLE users (
  id UUID PRIMARY KEY,
  name TEXT   -- ← no trailing comma
);
```

### 2. Missing IF NOT EXISTS
```sql
-- ❌ Fails on re-run
CREATE TABLE users (...);

-- ✅ Idempotent
CREATE TABLE IF NOT EXISTS users (...);
```

### 3. TIMESTAMPTZ not TIMESTAMPZ
```sql
-- ❌ WRONG
created_at TIMESTAMPZ DEFAULT NOW()

-- ✅ CORRECT
created_at TIMESTAMPTZ DEFAULT NOW()
```

### 4. JSONB default must be quoted
```sql
-- ❌ WRONG
content JSONB DEFAULT {}

-- ✅ CORRECT
content JSONB DEFAULT '{}'::JSONB
-- or
content JSONB NOT NULL DEFAULT '[]'::JSONB
```

### 5. Foreign key before referenced table exists
```sql
-- ❌ WRONG — child table created before parent
CREATE TABLE orders (
  user_id UUID REFERENCES users(id)  -- users doesn't exist yet!
);
CREATE TABLE users (id UUID PRIMARY KEY);

-- ✅ CORRECT — parent first, then child
CREATE TABLE users (id UUID PRIMARY KEY);
CREATE TABLE orders (
  user_id UUID REFERENCES users(id)
);

-- ✅ ALSO CORRECT — add FK after both exist
CREATE TABLE users (id UUID PRIMARY KEY);
CREATE TABLE orders (user_id UUID);
ALTER TABLE orders ADD CONSTRAINT fk_user
  FOREIGN KEY (user_id) REFERENCES users(id);
```

### 6. Reserved words as column names
```sql
-- ❌ WRONG
CREATE TABLE events (
  order INTEGER,     -- "order" is reserved
  user TEXT,         -- "user" is reserved
  group TEXT         -- "group" is reserved
);

-- ✅ CORRECT — use double quotes
CREATE TABLE events (
  "order" INTEGER,
  "user" TEXT,
  "group" TEXT
);

-- ✅ BETTER — just avoid reserved words
CREATE TABLE events (
  sort_order INTEGER,
  user_name TEXT,
  group_name TEXT
);
```

### 7. TEXT[] array syntax
```sql
-- ❌ WRONG
tags ARRAY[TEXT]

-- ✅ CORRECT
tags TEXT[]
-- or
tags TEXT ARRAY
```

## Insert / Seed Data

### 8. Column count mismatch
```sql
-- ❌ WRONG — 3 columns, 2 values
INSERT INTO users (id, name, email) VALUES ('abc', 'Seth');

-- ✅ CORRECT
INSERT INTO users (id, name, email) VALUES ('abc', 'Seth', 'seth@example.com');
```

### 9. UUID format must include hyphens
```sql
-- ❌ WRONG
INSERT INTO users (id) VALUES ('abc123');

-- ✅ CORRECT
INSERT INTO users (id) VALUES ('a1b2c3d4-e5f6-7890-abcd-ef1234567890');
```

### 10. Single quotes for values, double quotes for identifiers
```sql
-- ❌ WRONG
INSERT INTO users (name) VALUES ("Seth");   -- double quotes = column reference

-- ✅ CORRECT
INSERT INTO users (name) VALUES ('Seth');   -- single quotes = string value
```

### 11. Escaping single quotes in values
```sql
-- ❌ WRONG
INSERT INTO docs (title) VALUES ('Bob's Document');

-- ✅ CORRECT — double the quote
INSERT INTO docs (title) VALUES ('Bob''s Document');
-- or use dollar quoting
INSERT INTO docs (title) VALUES ($$Bob's Document$$);
```

### 12. NULL vs 'NULL'
```sql
-- ❌ WRONG — inserts the string "NULL"
INSERT INTO users (phone) VALUES ('NULL');

-- ✅ CORRECT — inserts actual NULL
INSERT INTO users (phone) VALUES (NULL);
```

### 13. FK reference to nonexistent row
```sql
-- ❌ WRONG — parent row doesn't exist
INSERT INTO orders (user_id) VALUES ('nonexistent-uuid');

-- ✅ FIX — insert parent first, or use ON CONFLICT
INSERT INTO users (id, name) VALUES ('uuid-here', 'Seth');
INSERT INTO orders (user_id) VALUES ('uuid-here');
```

### 14. Duplicate key on re-run
```sql
-- ❌ Fails on re-run
INSERT INTO peptides (id, name) VALUES ('uuid', 'BPC-157');

-- ✅ Idempotent
INSERT INTO peptides (id, name) VALUES ('uuid', 'BPC-157')
  ON CONFLICT (id) DO NOTHING;
-- or update on conflict
INSERT INTO peptides (id, name) VALUES ('uuid', 'BPC-157')
  ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name;
```

## RLS Policies

### 15. ENABLE RLS before creating policies
```sql
-- ❌ WRONG ORDER
CREATE POLICY "Users can see own org" ON users ...;
ALTER TABLE users ENABLE ROW LEVEL SECURITY;

-- ✅ CORRECT ORDER
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can see own org" ON users ...;
```

### 16. FOR ALL vs FOR SELECT/INSERT/UPDATE/DELETE
```sql
-- FOR ALL covers SELECT + INSERT + UPDATE + DELETE
CREATE POLICY "org_access" ON tasks FOR ALL USING (org_id = auth.uid());

-- But FOR ALL uses USING for both read AND write checks
-- If you need different logic for reads vs writes:
CREATE POLICY "read_access" ON tasks FOR SELECT USING (org_id = current_org());
CREATE POLICY "write_access" ON tasks FOR INSERT WITH CHECK (org_id = current_org());
```

### 17. Service role key bypasses RLS
```sql
-- If using service_role key in API routes, RLS does NOT protect you
-- You must manually filter:
const { data } = await supabase
  .from('tasks')
  .select('*')
  .eq('organization_id', orgId)  -- ← REQUIRED even with RLS
```

### 18. Policy name conflicts
```sql
-- ❌ WRONG — same name on same table
CREATE POLICY "access_policy" ON tasks FOR SELECT ...;
CREATE POLICY "access_policy" ON tasks FOR INSERT ...;  -- name collision!

-- ✅ CORRECT — unique names per table
CREATE POLICY "tasks_select_policy" ON tasks FOR SELECT ...;
CREATE POLICY "tasks_insert_policy" ON tasks FOR INSERT ...;
```

## Functions & Triggers

### 19. RETURNS vs RETURN
```sql
-- ❌ WRONG
CREATE FUNCTION my_func() RETURN INTEGER ...

-- ✅ CORRECT
CREATE FUNCTION my_func() RETURNS INTEGER ...
```

### 20. Dollar-quoting for function bodies
```sql
-- ❌ Fragile — breaks if function body contains single quotes
CREATE FUNCTION greet(name TEXT) RETURNS TEXT AS '
  BEGIN RETURN ''Hello '' || name; END;
' LANGUAGE plpgsql;

-- ✅ CORRECT — dollar quoting
CREATE FUNCTION greet(name TEXT) RETURNS TEXT AS $$
  BEGIN RETURN 'Hello ' || name; END;
$$ LANGUAGE plpgsql;
```

### 21. Trigger function must RETURN
```sql
-- ❌ WRONG — trigger function without RETURN
CREATE FUNCTION update_timestamp() RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  -- missing RETURN!
END;
$$ LANGUAGE plpgsql;

-- ✅ CORRECT
CREATE FUNCTION update_timestamp() RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;  -- ← required for BEFORE triggers
END;
$$ LANGUAGE plpgsql;
```

### 22. CREATE OR REPLACE for functions, not tables
```sql
-- ✅ Works for functions
CREATE OR REPLACE FUNCTION my_func() ...

-- ❌ Does NOT work for tables
CREATE OR REPLACE TABLE users ...  -- invalid syntax!

-- ✅ For tables, use IF NOT EXISTS
CREATE TABLE IF NOT EXISTS users ...
```

## Indexes

### 23. Index on expression needs parens
```sql
-- ❌ WRONG
CREATE INDEX idx_lower_email ON users (LOWER email);

-- ✅ CORRECT
CREATE INDEX idx_lower_email ON users (LOWER(email));
```

### 24. Partial index WHERE clause
```sql
-- ✅ Partial index — only indexes unread alerts (much smaller)
CREATE INDEX idx_unread_alerts ON alerts (organization_id)
  WHERE is_read = false;
```

## Supabase-Specific

### 25. uuid-ossp extension must be enabled first
```sql
-- ❌ WRONG — uuid_generate_v4() doesn't exist yet
CREATE TABLE users (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4()
);

-- ✅ CORRECT — enable extension first
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE TABLE users (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4()
);

-- ✅ ALTERNATIVE — use gen_random_uuid() (built-in, no extension needed)
CREATE TABLE users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid()
);
```

### 26. auth.jwt() only works in RLS context
```sql
-- auth.jwt() returns NULL outside of a Supabase client request
-- Don't use it in triggers or manual SQL queries
-- Use it ONLY in RLS policies

-- ✅ CORRECT — in RLS policy
CREATE POLICY "org_access" ON tasks
  USING (organization_id = (auth.jwt() -> 'app_metadata' ->> 'organization_id')::UUID);
```

### 27. Supabase Storage paths
```sql
-- Storage buckets must be created before use
INSERT INTO storage.buckets (id, name, public)
  VALUES ('coa-documents', 'coa-documents', false);
-- Set public = false for sensitive documents
```

### 28. BIGINT vs INTEGER for file sizes
```sql
-- ❌ INTEGER maxes out at ~2GB
file_size INTEGER

-- ✅ BIGINT handles any file size
file_size BIGINT
```

### 29. INET type for IP addresses
```sql
-- ❌ TEXT works but no validation
ip_address TEXT

-- ✅ INET validates and allows network operations
ip_address INET
```

### 30. DECIMAL precision for currency/quantities
```sql
-- ❌ FLOAT has rounding issues
price FLOAT

-- ✅ DECIMAL with explicit precision
price DECIMAL(10, 2)        -- up to 99,999,999.99
quantity DECIMAL(12, 4)      -- up to 99,999,999.9999
molecular_weight DECIMAL(10, 4)
```
