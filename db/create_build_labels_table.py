#!/usr/bin/env python3
"""
Create build_labels table for storing labels/notes on builds.
Run this once to initialize the table.
"""

import sqlite3
import sys

def create_build_labels_table(db_path):
    """Create the build_labels table if it doesn't exist."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create table with foreign key constraint
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS build_labels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_name TEXT NOT NULL,
            build_number INTEGER NOT NULL,
            label TEXT NOT NULL,
            created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(job_name, build_number),
            FOREIGN KEY(job_name, build_number) REFERENCES performance_data(job_name, build_number)
        )
    ''')

    # Create index for faster lookup
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_build_labels_job_build
        ON build_labels(job_name, build_number)
    ''')

    conn.commit()
    conn.close()

    print(f"✓ build_labels table created successfully in {db_path}")

if __name__ == '__main__':
    db_path = sys.argv[1] if len(sys.argv) > 1 else 'tpms.db'
    create_build_labels_table(db_path)
