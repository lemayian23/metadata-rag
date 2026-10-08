ALTER TABLE chunks ADD COLUMN IF NOT EXISTS raw_content TEXT;
UPDATE chunks SET raw_content = content WHERE raw_content IS NULL;
ALTER TABLE chunks ALTER COLUMN raw_content SET NOT NULL;
