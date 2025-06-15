from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from database import db, AdminUser, Product, StockMovement, StoreSale
import os
from datetime import datetime, timedelta
import json
from sqlalchemy import or_

# Flask-Admin importları
from flask_admin import Admin
from flask_admin.contrib.sqla import ModelView

# Flask uygulaması
app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///stok_takip.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Türkiye saati için timezone ayarı
TURKEY_TIMEZONE = timedelta(hours=3)

# Veritabanı başlat
db.init_app(app)

# Giriş yönetimi
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return AdminUser.query.get(int(user_id))

# Türkiye saatini döndüren yardımcı fonksiyon
def get_turkey_time():
    return datetime.utcnow() + TURKEY_TIMEZONE

# Veritabanını oluştur
with app.app_context():
    db.create_all()
    
    # İlk admin kullanıcısını oluştur (eğer yoksa)
    if not AdminUser.query.first():
        admin = AdminUser(
            username='admin',
            password=generate_password_hash('admin123'),
            email='admin@example.com'
        )
        db.session.add(admin)
        db.session.commit()

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        email = request.form['email']
        
        if AdminUser.query.filter_by(username=username).first():
            flash('Bu kullanıcı adı zaten kullanılıyor!')
            return redirect(url_for('register'))
        
        admin_user = AdminUser(
            username=username,
            password=generate_password_hash(password),
            email=email
        )
        db.session.add(admin_user)
        db.session.commit()
        flash('Kayıt başarılı! Giriş yapabilirsiniz.')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        admin_user = AdminUser.query.filter_by(username=username).first()
        
        if admin_user and check_password_hash(admin_user.password, password):
            login_user(admin_user)
            return redirect(url_for('dashboard'))
        
        flash('Geçersiz kullanıcı adı veya şifre!')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    # Sadece giriş yapan kullanıcının ürünlerini getir
    products = Product.query.filter_by(admin_id=current_user.id).all()
    low_stock_products = []
    for p in products:
        if p.reyon_quantity <= p.minimum_stock_level or p.depo_quantity <= p.minimum_stock_level:
            low_stock_products.append(p)
    
    if low_stock_products:
        flash('Kritik stok seviyesi uyarısı! Bazı ürünlerin stok seviyesi minimum değerin altında.', 'warning sound-alert')
    return render_template('dashboard.html', products=products, low_stock_products=low_stock_products)

@app.route('/add_product', methods=['GET', 'POST'])
@login_required
def add_product():
    if request.method == 'POST':
        barcode = request.form['barcode']
        product_code = request.form['product_code']
        quantity = int(request.form['quantity'])
        unit_cost = float(request.form['unit_cost'])
        
        # Mevcut ürünü kontrol et
        existing_product = Product.query.filter_by(
            admin_id=current_user.id,
            barcode=barcode
        ).first()
        
        if existing_product:
            # Ürün zaten varsa, stok güncelle
            # Ağırlıklı ortalama maliyet hesapla
            current_total_cost = existing_product.quantity * existing_product.unit_cost
            new_total_cost = quantity * unit_cost
            total_quantity = existing_product.quantity + quantity
            new_unit_cost = (current_total_cost + new_total_cost) / total_quantity
            
            # Stok ve maliyet güncelle
            existing_product.depo_quantity += quantity
            existing_product.quantity += quantity
            existing_product.unit_cost = new_unit_cost
            
            db.session.commit()
            
            # Stok hareketi kaydı oluştur
            movement = StockMovement(
                product_id=existing_product.id,
                movement_type='Stok Girişi',
                quantity=quantity,
                description=f'Depoya stok girişi yapıldı (Birim Maliyet: {unit_cost} TL, Yeni Ortalama Maliyet: {new_unit_cost:.2f} TL)',
                admin_id=current_user.id
            )
            db.session.add(movement)
            db.session.commit()
            
            flash(f'{existing_product.name} ürününe {quantity} adet stok girişi yapıldı. Yeni ortalama maliyet: {new_unit_cost:.2f} TL', 'success')
            return redirect(url_for('dashboard'))
        
        # Yeni ürün ekle
        product = Product(
            product_code=product_code,
            barcode=barcode,
            name=request.form['name'],
            description=request.form['description'],
            quantity=quantity,
            reyon_quantity=0,  # Başlangıçta tüm stok depoda
            depo_quantity=quantity,
            unit=request.form['unit'],
            category=request.form['category'],
            unit_cost=unit_cost,
            admin_id=current_user.id
        )
        db.session.add(product)
        db.session.commit()
        
        # İlk stok hareketi kaydı
        movement = StockMovement(
            product_id=product.id,
            movement_type='Stok Girişi',
            quantity=quantity,
            description=f'İlk stok girişi (Birim Maliyet: {unit_cost} TL)',
            admin_id=current_user.id
        )
        db.session.add(movement)
        db.session.commit()
        
        flash('Yeni ürün başarıyla eklendi!', 'success')
        return redirect(url_for('dashboard'))
    return render_template('add_product.html')

@app.route('/stock_movement', methods=['GET', 'POST'])
@login_required
def stock_movement():
    if request.method == 'POST':
        product_id = request.form['product_id']
        movement_type = request.form['movement_type']
        quantity = int(request.form['quantity'])
        description = request.form['description']
        
        # Ürünün kullanıcıya ait olduğunu kontrol et
        product = Product.query.filter_by(id=product_id, admin_id=current_user.id).first()
        if not product:
            flash('Bu ürün üzerinde işlem yapma yetkiniz yok!', 'error')
            return redirect(url_for('stock_movement'))
            
        if movement_type == 'Depodan Reyona':
            if product.depo_quantity >= quantity:
                product.depo_quantity -= quantity
                product.reyon_quantity += quantity
            else:
                flash('Depoda yetersiz stok!', 'error')
                return redirect(url_for('stock_movement'))
        else:  # Reyondan Depoya
            if product.reyon_quantity >= quantity:
                product.reyon_quantity -= quantity
                product.depo_quantity += quantity
            else:
                flash('Reyonda yetersiz stok!', 'error')
                return redirect(url_for('stock_movement'))
        
        movement = StockMovement(
            product_id=product_id,
            movement_type=movement_type,
            quantity=quantity,
            description=description,
            admin_id=current_user.id,
            created_at=get_turkey_time()
        )
        
        db.session.add(movement)
        db.session.commit()

        # Stok seviyesi kontrolü
        warning_messages = []
        if product.reyon_quantity <= product.minimum_stock_level:
            warning_messages.append(f'Reyon stok seviyesi kritik! (Mevcut: {product.reyon_quantity})')
        if product.depo_quantity <= product.minimum_stock_level:
            warning_messages.append(f'Depo stok seviyesi kritik! (Mevcut: {product.depo_quantity})')
        
        if warning_messages:
            flash(f'UYARI: {product.name} ürünü için: ' + ' | '.join(warning_messages), 'warning sound-alert')
        else:
            flash('Stok hareketi başarıyla kaydedildi!', 'info')
            
        return redirect(url_for('dashboard'))
    
    # Sadece kullanıcının kendi ürünlerini listele
    products = Product.query.filter_by(admin_id=current_user.id).all()
    return render_template('stock_movement.html', products=products)

@app.route('/store_sales', methods=['GET', 'POST'])
@login_required
def store_sales():
    if request.method == 'POST':
        product_id = request.form['product_id']
        quantity = int(request.form['quantity'])
        sale_price = float(request.form['sale_price'])
        
        # Ürünün kullanıcıya ait olduğunu kontrol et
        product = Product.query.filter_by(id=product_id, admin_id=current_user.id).first()
        if not product:
            flash('Bu ürün üzerinde işlem yapma yetkiniz yok!', 'error')
            return redirect(url_for('store_sales'))
        
        # Depo stokunu kontrol et
        if product.depo_quantity < quantity:
            flash('Depoda yetersiz stok!', 'error')
            return redirect(url_for('store_sales'))
        
        # Satış işlemini gerçekleştir
        total_amount = quantity * sale_price
        total_cost = quantity * product.unit_cost
        profit = total_amount - total_cost
        
        # Satış kaydı oluştur
        sale = StoreSale(
            product_id=product_id,
            quantity=quantity,
            sale_price=sale_price,
            total_amount=total_amount,
            total_cost=total_cost,
            profit=profit,
            admin_id=current_user.id
        )
        db.session.add(sale)
        
        # Stok güncelle
        product.depo_quantity -= quantity
        product.quantity -= quantity
        
        # Stok hareketi kaydı
        movement = StockMovement(
            product_id=product_id,
            movement_type='Satış',
            quantity=-quantity,
            description=f'Mağaza satışı (Satış Fiyatı: {sale_price} TL, Toplam Tutar: {total_amount} TL)',
            admin_id=current_user.id
        )
        db.session.add(movement)
        
        db.session.commit()
        flash('Satış başarıyla gerçekleştirildi!', 'success')
        return redirect(url_for('store_sales'))
    
    # Sadece depoda stok olan ürünleri getir
    products = Product.query.filter(
        Product.admin_id == current_user.id,
        Product.depo_quantity > 0
    ).all()
    
    # Son satışları getir
    sales = StoreSale.query.filter_by(admin_id=current_user.id).order_by(StoreSale.created_at.desc()).limit(10).all()
    
    return render_template('store_sales.html', products=products, sales=sales)

@app.route('/search_product', methods=['GET'])
@login_required
def search_product():
    search_term = request.args.get('search', '')
    if search_term:
        products = Product.query.filter(
            Product.admin_id == current_user.id,
            or_(
                Product.name.ilike(f'%{search_term}%'),
                Product.barcode.ilike(f'%{search_term}%'),
                Product.product_code.ilike(f'%{search_term}%')
            )
        ).all()
    else:
        products = []
    return render_template('search_product.html', products=products)

@app.route('/finance')
@login_required
def finance():
    products = Product.query.filter_by(admin_id=current_user.id).all()
    sales = StoreSale.query.filter_by(admin_id=current_user.id).all()
    
    # Toplam stok değerlerini hesapla
    total_stock_value = sum(p.quantity * p.unit_cost for p in products)
    reyon_stock_value = sum(p.reyon_quantity * p.unit_cost for p in products)
    depo_stock_value = sum(p.depo_quantity * p.unit_cost for p in products)
    
    # Satış istatistikleri
    total_sales = sum(s.sale_price * s.quantity for s in sales)
    total_cost = sum(s.total_cost for s in sales)
    total_profit = total_sales - total_cost
    
    # Ürün bazlı detaylı bilgiler
    product_details = []
    for product in products:
        # Ürünün satışlarını filtrele
        product_sales = [s for s in sales if s.product_id == product.id]
        
        # Satış istatistikleri
        product_total_sales = sum(s.sale_price * s.quantity for s in product_sales)
        product_total_cost = sum(s.total_cost for s in product_sales)
        product_profit = product_total_sales - product_total_cost
        
        # Stok değerleri
        total_stock_value = product.quantity * product.unit_cost
        reyon_stock_value = product.reyon_quantity * product.unit_cost
        depo_stock_value = product.depo_quantity * product.unit_cost
        
        product_details.append({
            'name': product.name,
            'total_stock': product.quantity,
            'reyon_stock': product.reyon_quantity,
            'depo_stock': product.depo_quantity,
            'unit_cost': product.unit_cost,
            'total_stock_value': total_stock_value,
            'reyon_stock_value': reyon_stock_value,
            'depo_stock_value': depo_stock_value,
            'total_sales': product_total_sales,
            'total_cost': product_total_cost,
            'profit': product_profit
        })
    
    return render_template('finance.html',
                         products=products,
                         product_details=product_details,
                         total_stock_value=total_stock_value,
                         reyon_stock_value=reyon_stock_value,
                         depo_stock_value=depo_stock_value,
                         total_sales=total_sales,
                         total_profit=total_profit,
                         total_cost=total_cost)

@app.route('/check_product')
@login_required
def check_product():
    barcode = request.args.get('barcode')
    product_code = request.args.get('product_code')
    
    if barcode:
        product = Product.query.filter_by(barcode=barcode, admin_id=current_user.id).first()
    elif product_code:
        product = Product.query.filter_by(product_code=product_code, admin_id=current_user.id).first()
    else:
        return jsonify({'exists': False})
    
    if product:
        return jsonify({
            'exists': True,
            'product': {
                'barcode': product.barcode,
                'product_code': product.product_code,
                'name': product.name,
                'category': product.category,
                'unit': product.unit
            }
        })
    
    return jsonify({'exists': False})

@app.route('/delete_product/<int:product_id>', methods=['POST'])
@login_required
def delete_product(product_id):
    product = Product.query.get_or_404(product_id)
    
    # Ürüne ait tüm stok hareketlerini sil
    StockMovement.query.filter_by(product_id=product_id).delete()
    
    # Ürüne ait tüm mağaza satışlarını sil
    StoreSale.query.filter_by(product_id=product_id).delete()
    
    # Ürünü sil
    db.session.delete(product)
    db.session.commit()
    
    flash('Ürün başarıyla silindi.', 'success')
    return redirect(url_for('search_product'))

@app.route('/reset_db')
@login_required
def reset_db():
    try:
        # Tüm tabloları sil ve yeniden oluştur
        db.drop_all()
        db.create_all()
        flash('Veritabanı başarıyla sıfırlandı.', 'success')
    except Exception as e:
        flash(f'Veritabanı sıfırlanırken hata oluştu: {str(e)}', 'error')
    return redirect(url_for('dashboard'))

# Flask-Admin için giriş kontrolü
class AuthModelView(ModelView):
    def is_accessible(self):
        return current_user.is_authenticated
    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('login'))

# Admin panel views
class AdminUserView(AuthModelView):
    # Sütun başlıklarını Türkçe yapma
    column_labels = {
        'username': 'Kullanıcı Adı',
        'email': 'E-posta',
        'created_at': 'Oluşturulma Tarihi'
    }
    # Form etiketlerini Türkçe yapma
    form_labels = {
        'username': 'Kullanıcı Adı',
        'email': 'E-posta',
        'password': 'Şifre'
    }
    column_list = ['username', 'email', 'created_at']
    form_columns = ['username', 'email', 'password']

class ProductView(AuthModelView):
    # Sütun başlıklarını Türkçe yapma
    column_labels = {
        'name': 'Ürün Adı',
        'product_code': 'Ürün Kodu',
        'barcode': 'Barkod',
        'category': 'Kategori',
        'quantity': 'Toplam Miktar',
        'reyon_quantity': 'Reyon Miktarı',
        'depo_quantity': 'Depo Miktarı',
        'unit': 'Birim',
        'unit_cost': 'Birim Maliyet'
    }
    column_list = ['name', 'product_code', 'barcode', 'category', 'quantity', 'reyon_quantity', 'depo_quantity', 'unit', 'unit_cost']
    form_columns = ['name', 'product_code', 'barcode', 'category', 'quantity', 'reyon_quantity', 'depo_quantity', 'unit', 'unit_cost', 'minimum_stock_level']

class StockMovementView(AuthModelView):
    # Sütun başlıklarını Türkçe yapma
    column_labels = {
        'product_id': 'Ürün',
        'movement_type': 'Hareket Tipi',
        'quantity': 'Miktar',
        'created_at': 'Tarih'
    }
    column_list = ['product_id', 'movement_type', 'quantity', 'created_at']
    form_columns = ['product_id', 'movement_type', 'quantity']

class StoreSaleView(AuthModelView):
    # Sütun başlıklarını Türkçe yapma
    column_labels = {
        'product': 'Ürün',
        'quantity': 'Miktar',
        'sale_price': 'Satış Fiyatı',
        'total_amount': 'Toplam Tutar',
        'total_cost': 'Toplam Maliyet',
        'profit': 'Kar',
        'created_at': 'Tarih'
    }
    column_list = ['product', 'quantity', 'sale_price', 'total_amount', 'total_cost', 'profit', 'created_at']
    form_columns = ['product', 'quantity', 'sale_price']

# Admin panel setup
admin_panel = Admin(app, name='Yönetim Paneli', template_mode='bootstrap3')
admin_panel.add_view(AdminUserView(AdminUser, db.session, name='Kullanıcılar'))
admin_panel.add_view(ProductView(Product, db.session, name='Ürünler'))
admin_panel.add_view(StockMovementView(StockMovement, db.session, name='Stok Hareketleri'))
admin_panel.add_view(StoreSaleView(StoreSale, db.session, name='Mağaza Satışları'))

# Uygulama başlat
if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # Sadece tabloları oluştur, varsa değiştirme
    app.run(debug=True)
