import sqlite3

DB_NAME = "items.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            button_name TEXT NOT NULL,
            content_type TEXT NOT NULL,  -- 'video' or 'link'
            file_id TEXT,                -- video ke liye
            url TEXT,                    -- link ke liye
            price INTEGER NOT NULL       -- amount in paise (₹ * 100)
        )
    """)
    conn.commit()
    conn.close()

def add_item(button_name, content_type, file_id, url, price_rupees):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO items(button_name, content_type, file_id, url, price)
        VALUES (?, ?, ?, ?, ?)
    """, (button_name, content_type, file_id, url, price_rupees * 100))
    conn.commit()
    conn.close()

def get_all_items():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT id, button_name, price FROM items")
    rows = cur.fetchall()
    conn.close()
    return rows

def get_item(item_id):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        SELECT id, button_name, content_type, file_id, url, price
        FROM items WHERE id=?
    """, (item_id,))
    row = cur.fetchone()
    conn.close()
    return row
  
