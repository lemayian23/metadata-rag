ALTER TABLE chunks ADD COLUMN IF NOT EXISTS modality TEXT DEFAULT 'text';
UPDATE chunks SET modality = 'text' WHERE modality IS NULL;
ALTER TABLE chunks ALTER COLUMN modality SET NOT NULL;
CREATE INDEX IF NOT EXISTS idx_chunks_modality ON chunks(modality);
