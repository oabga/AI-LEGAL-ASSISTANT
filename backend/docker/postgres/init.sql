-- Chỉ cài extension ở đây vì CREATE EXTENSION cần quyền superuser, còn Alembic
-- chạy bằng user ứng dụng. Toàn bộ bảng do migration trong backend/alembic quản lý.

-- PostgreSQL không có từ điển full-text cho tiếng Việt, nên chiến lược tìm kiếm
-- là bỏ dấu bằng unaccent rồi dùng cấu hình 'simple', kèm pg_trgm để so khớp
-- gần đúng khi người dùng gõ thiếu/sai dấu.
CREATE EXTENSION IF NOT EXISTS unaccent;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- unaccent() mặc định là STABLE nên không dùng được trong generated column.
-- Bọc lại thành IMMUTABLE để tạo được cột tsvector generated + index GIN.
CREATE OR REPLACE FUNCTION immutable_unaccent(text)
RETURNS text
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
STRICT
AS $$ SELECT public.unaccent('public.unaccent'::regdictionary, $1) $$;
