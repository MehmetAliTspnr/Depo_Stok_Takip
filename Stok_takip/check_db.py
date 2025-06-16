import sqlite3
from tabulate import tabulate
import os

def print_table_data(db_handler, table_name):
    try:
        db_handler.execute(f"SELECT * FROM {table_name}")
        table_rows = db_handler.fetchall()
        
        # Sütun isimlerini al
        db_handler.execute(f"PRAGMA table_info({table_name})")
        column_names = [col[1] for col in db_handler.fetchall()]
        
        if table_rows:
            print(f"\n{table_name.upper()} Tablosu Kayıtları:")
            print(tabulate(table_rows, headers=column_names, tablefmt='grid'))
        else:
            print(f"\n{table_name.upper()} tablosunda kayıt bulunamadı.")
    except sqlite3.Error as e:
        print(f"Tablo verileri alınırken hata oluştu: {e}")

def main():
    db_file = 'stok_takip.db'
    
    if not os.path.exists(db_file):
        print(f"Hata: {db_file} dosyası bulunamadı!")
        return
        
    try:
        # Veritabanına bağlan
        db_connection = sqlite3.connect(db_file)
        db_handler = db_connection.cursor()

        # Tabloları listele
        db_handler.execute("SELECT name FROM sqlite_master WHERE type='table';")
        database_tables = db_handler.fetchall()

        if not database_tables:
            print("Veritabanında tablo bulunamadı!")
            return

        print("Veritabanındaki tablolar:")
        for table in database_tables:
            print(f"- {table[0]}")
            print_table_data(db_handler, table[0])

    except sqlite3.Error as e:
        print(f"Veritabanı işlemi sırasında hata oluştu: {e}")
    finally:
        if 'db_connection' in locals():
            db_connection.close()

if __name__ == "__main__":
    main() 