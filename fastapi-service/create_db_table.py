"""Database setup script - creates verification_runs table."""

import asyncio
import asyncpg
import os

# Database connection settings
DB_HOST = os.getenv("DB_HOST") 
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

# Table creation DDL
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS verification_runs (
    -- Primary identifiers
    id BIGSERIAL PRIMARY KEY,
    run_id VARCHAR(255) NOT NULL UNIQUE,
    trace_id VARCHAR(255),
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    processing_time_seconds NUMERIC(10, 6),
    
    -- External metadata (from Kafka)
    external_request_id VARCHAR(255),
    external_s3_path VARCHAR(500),
    external_iin VARCHAR(12),
    external_first_name VARCHAR(255),
    external_last_name VARCHAR(255),
    external_second_name VARCHAR(255),
    
    -- Pipeline status
    status VARCHAR(50) NOT NULL CHECK (status IN ('success', 'error')),
    
    -- HTTP error fields (populated only when status='error')
    http_error_code VARCHAR(100),
    http_error_message TEXT,
    http_error_category VARCHAR(100),
    http_error_retryable BOOLEAN,
    
    -- Extracted data (populated only when status='success')
    extracted_fio VARCHAR(500),
    extracted_doc_date VARCHAR(50),
    extracted_single_doc_type BOOLEAN,
    extracted_doc_type_known BOOLEAN,
    extracted_doc_type VARCHAR(255),
    
    -- Business rule checks (populated only when status='success')
    rule_fio_match BOOLEAN,
    rule_doc_date_valid BOOLEAN,
    rule_doc_type_known BOOLEAN,
    rule_single_doc_type BOOLEAN,
    rule_verdict BOOLEAN,
    rule_errors JSONB DEFAULT '[]',
    
    -- Metadata
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

# Create indexes (run_id excluded - UNIQUE constraint already creates index)
CREATE_INDEXES_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_verification_runs_trace_id ON verification_runs(trace_id);",
    "CREATE INDEX IF NOT EXISTS idx_verification_runs_created_at ON verification_runs(created_at DESC);",
    "CREATE INDEX IF NOT EXISTS idx_verification_runs_external_request_id ON verification_runs(external_request_id);",
    "CREATE INDEX IF NOT EXISTS idx_verification_runs_external_iin ON verification_runs(external_iin);",
    "CREATE INDEX IF NOT EXISTS idx_verification_runs_status ON verification_runs(status);",
    "CREATE INDEX IF NOT EXISTS idx_verification_runs_inserted_at ON verification_runs(inserted_at DESC);",
]

# Add comments
ADD_COMMENTS_SQL = [
    "COMMENT ON TABLE verification_runs IS 'Stores verification pipeline execution results from final.json';",
    "COMMENT ON COLUMN verification_runs.run_id IS 'Unique UUID for each pipeline run';",
    "COMMENT ON COLUMN verification_runs.trace_id IS 'Request trace ID for distributed tracing';",
    "COMMENT ON COLUMN verification_runs.status IS 'Pipeline outcome: success or error';",
    "COMMENT ON COLUMN verification_runs.rule_verdict IS 'Final business rule verdict (true=approved, false=rejected)';",
    "COMMENT ON COLUMN verification_runs.rule_errors IS 'Array of rule error codes (e.g., [\"FIO_MISMATCH\"])';",
]


async def setup_database():
    """Connect to PostgreSQL and create table with indexes."""
    print(f"🔧 Connecting to {DB_HOST}:{DB_PORT}/{DB_NAME}...")

    try:
        # Create connection
        conn = await asyncpg.connect(
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            timeout=10.0,
        )

        print("✅ Connected successfully!")

        # Create table
        print("\n📋 Creating table 'verification_runs'...")
        await conn.execute(CREATE_TABLE_SQL)
        print("✅ Table created!")

        # Create indexes
        print("\n🔍 Creating indexes...")
        for idx_sql in CREATE_INDEXES_SQL:
            await conn.execute(idx_sql)
            print(f"  ✅ {idx_sql.split('idx_')[1].split(' ')[0]}")

        # Add comments
        print("\n💬 Adding comments...")
        for comment_sql in ADD_COMMENTS_SQL:
            await conn.execute(comment_sql)
        print("✅ Comments added!")

        # Verify table
        print("\n🔍 Verifying table structure...")
        columns = await conn.fetch("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'verification_runs'
            ORDER BY ordinal_position
        """)

        print(f"\n📊 Table has {len(columns)} columns:")
        for col in columns[:5]:  # Show first 5
            print(f"  - {col['column_name']}: {col['data_type']}")
        print(f"  ... and {len(columns) - 5} more columns")

        # Check record count
        count = await conn.fetchval("SELECT COUNT(*) FROM verification_runs")
        print(f"\n📈 Current records: {count}")

        # Close connection
        await conn.close()
        print("\n🎉 Database setup complete!")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(setup_database())
