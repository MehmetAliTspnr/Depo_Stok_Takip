from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, timedelta

db = SQLAlchemy()

# Türkiye saati için timezone ayarı
TURKEY_TIMEZONE = timedelta(hours=3)

def get_turkey_time():
    return datetime.utcnow() + TURKEY_TIMEZONE

# Admin → AdminUser olarak değiştirildi
class AdminUser(UserMixin, db.Model):
    __tablename__ = 'admin'  # Veritabanındaki tablo adı aynı kalıyor
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=get_turkey_time)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_code = db.Column(db.String(50), nullable=False)  # Özel ürün numarası
    barcode = db.Column(db.String(50), nullable=False)  # Barkod numarası
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    quantity = db.Column(db.Integer, default=0)  # Toplam miktar
    reyon_quantity = db.Column(db.Integer, default=0)  # Reyondaki miktar
    depo_quantity = db.Column(db.Integer, default=0)  # Depodaki miktar
    unit = db.Column(db.String(20), nullable=False)  # Adet, kg, metre vb.
    category = db.Column(db.String(50))  # Ürün kategorisi
    minimum_stock_level = db.Column(db.Integer, default=10)  # Minimum stok seviyesi
    unit_cost = db.Column(db.Float, nullable=False)  # Birim maliyet
    created_at = db.Column(db.DateTime, default=get_turkey_time)
    updated_at = db.Column(db.DateTime, default=get_turkey_time, onupdate=get_turkey_time)
    admin_id = db.Column(db.Integer, db.ForeignKey('admin.id'), nullable=False)  # Kullanıcı ilişkisi

    # Kullanıcı bazlı benzersiz kısıtlamalar
    __table_args__ = (
        db.UniqueConstraint('product_code', 'admin_id', name='uix_product_code_admin'),
        db.UniqueConstraint('barcode', 'admin_id', name='uix_barcode_admin'),
    )

class StockMovement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    movement_type = db.Column(db.String(20), nullable=False)  # Depodan Reyona veya Reyondan Depoya
    quantity = db.Column(db.Integer, nullable=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=get_turkey_time)  # Türkiye saati
    admin_id = db.Column(db.Integer, db.ForeignKey('admin.id'), nullable=False)  # admin tablosuna bağlı

class StoreSale(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    sale_price = db.Column(db.Float, nullable=False)
    total_amount = db.Column(db.Float, nullable=False)  # quantity * sale_price
    total_cost = db.Column(db.Float, nullable=False)    # quantity * product.unit_cost
    profit = db.Column(db.Float, nullable=False)        # total_amount - total_cost
    created_at = db.Column(db.DateTime, default=get_turkey_time)
    admin_id = db.Column(db.Integer, db.ForeignKey('admin.id'), nullable=False)
    
    product = db.relationship('Product', backref='store_sales')
    admin = db.relationship('AdminUser', backref='store_sales')
