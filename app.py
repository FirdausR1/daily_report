# app.py
from flask import Flask, render_template, request, redirect, session, send_file
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from io import BytesIO
import openpyxl
from datetime import datetime
app = Flask(__name__)
app.secret_key = 'geodipa_secret_key'
DATABASE = 'laporan.db'

# Inisialisasi database
def init_db():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nama TEXT,
            username TEXT UNIQUE,
            password TEXT,
            role TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS laporan (
             id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_user INTEGER,
            hari TEXT,
            tanggal TEXT,
            uraian TEXT,
            jenis_pekerjaan TEXT,
            equipment TEXT,
            status TEXT,
            keterangan TEXT,
            catatan TEXT,
            validasi TEXT DEFAULT 'Menunggu',
            validator TEXT,
            waktu_validasi TEXT,
            FOREIGN KEY (id_user) REFERENCES users(id)
        )
    ''')
    c.execute("SELECT * FROM users WHERE username='admin'")
    if not c.fetchone():
        c.execute("INSERT INTO users (nama, username, password, role) VALUES (?, ?, ?, ?)",
                  ('Admin', 'admin', generate_password_hash('admin123'), 'admin'))
    conn.commit()
    conn.close()

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = c.fetchone()
        conn.close()
        if user and check_password_hash(user[3], password):
            session['user_id'] = user[0]
            session['username'] = user[2]
            session['role'] = user[4]
            return redirect('/')
        return render_template('login.html', error='Login gagal!')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect('/login')

    role = session['role']
    username = session['username']

    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM laporan")
    total_laporan = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM users")
    total_user = c.fetchone()[0]
    c.execute("SELECT jenis_pekerjaan, COUNT(*) FROM laporan GROUP BY jenis_pekerjaan")
    ringkasan = c.fetchall()
    conn.close()

    return render_template('index.html', username=username, role=role,
                           total_laporan=total_laporan,
                           total_user=total_user,
                           ringkasan=ringkasan)

@app.route('/input', methods=['GET', 'POST'])
def input_laporan():
    if 'user_id' not in session or session['role'] not in ['admin', 'teknisi']:
        return redirect('/login')
    if request.method == 'POST':
        data = (
            session['user_id'],
            request.form['hari'],
            request.form['tanggal'],
            request.form['uraian'],
            request.form['jenis'],
            request.form['equipment'],
            request.form['status'],
            request.form['keterangan'],
            request.form['catatan']
        )
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        c.execute('''
            INSERT INTO laporan (id_user, hari, tanggal, uraian, jenis_pekerjaan, equipment, status, keterangan, catatan)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', data)
        conn.commit()
        conn.close()
        return redirect('/laporan')
    return render_template('input.html')

@app.route('/laporan')
def lihat_laporan():
    if 'user_id' not in session:
        return redirect('/login')

    filter_tanggal = request.args.get('tanggal', '')
    filter_jenis = request.args.get('jenis', '')

    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    query = '''
        SELECT l.id, l.tanggal, l.hari, l.jenis_pekerjaan, l.equipment, l.status,
               l.keterangan, l.catatan, u.nama AS teknisi,
               l.validasi, l.validator, l.waktu_validasi
        FROM laporan l
        JOIN users u ON l.id_user = u.id
        WHERE 1=1
    '''
    params = []
    
    if filter_tanggal:
        query += " AND l.tanggal = ?"
        params.append(filter_tanggal)
    if filter_jenis:
        query += " AND l.jenis_pekerjaan LIKE ?"
        params.append(f"%{filter_jenis}%")

    query += " ORDER BY l.tanggal DESC"
    c.execute(query, params)
    rows = c.fetchall()
    conn.close()

    return render_template('laporan.html', laporan=rows,
                           filter_tanggal=filter_tanggal, filter_jenis=filter_jenis,role=session['role'])
@app.route('/laporan/validasi/<int:laporan_id>')
def validasi_laporan(laporan_id):
    if 'user_id' not in session or session['role'] != 'supervisor':
        return redirect('/login')
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("""UPDATE laporan 
                 SET validasi='Tervalidasi', validator=?, waktu_validasi=? 
                 WHERE id=?""",
              (session['username'], now, laporan_id))
    conn.commit()
    conn.close()
    return redirect('/laporan')

@app.route('/laporan/batal_validasi/<int:laporan_id>')
def batal_validasi_laporan(laporan_id):
    if 'user_id' not in session or session['role'] != 'supervisor':
        return redirect('/login')
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("""UPDATE laporan 
                 SET validasi='Menunggu', validator=NULL, waktu_validasi=NULL 
                 WHERE id=?""", (laporan_id,))
    conn.commit()
    conn.close()
    return redirect('/laporan')

@app.route('/export-excel')
def export_excel():
    if 'user_id' not in session:
        return redirect('/login')

    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('''
        SELECT l.tanggal, l.hari, l.jenis_pekerjaan, l.equipment,
               l.status, l.keterangan, l.catatan, u.nama
        FROM laporan l
        JOIN users u ON l.id_user = u.id
        ORDER BY l.tanggal DESC
    ''')
    data = c.fetchall()
    conn.close()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Laporan Maintenance'
    ws.append(['Tanggal', 'Hari', 'Jenis Pekerjaan', 'Equipment', 'Status',
               'Keterangan', 'Catatan', 'Nama Teknisi'])
    for row in data:
        ws.append(row)
    output = BytesIO()
    wb.save(output)
    output.seek(0)

    return send_file(output, download_name="laporan_maintenance.xlsx", as_attachment=True)

@app.route('/users')
def kelola_users():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect('/login')
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("SELECT * FROM users")
    users = c.fetchall()
    conn.close()
    return render_template('users.html', users=users)

@app.route('/users/add', methods=['GET', 'POST'])
@app.route('/users/edit/<int:user_id>', methods=['GET', 'POST'])
def tambah_edit_user(user_id=None):
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect('/login')
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    user = None
    if user_id:
        c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user = c.fetchone()

    if request.method == 'POST':
            nama = request.form['nama']
            username = request.form['username']
            role = request.form['role']
            password = request.form['password']

    # Cek apakah username sudah digunakan user lain
            if user:
                c.execute("SELECT * FROM users WHERE username=? AND id != ?", (username, user_id))
            else:
                c.execute("SELECT * FROM users WHERE username=?", (username,))
            existing = c.fetchone()
            if existing:
                conn.close()
                return render_template('user_form.html', user=user, error="Username sudah digunakan.")

            if user:  # update
                if password:
                    password = generate_password_hash(password)
                    c.execute("UPDATE users SET nama=?, username=?, password=?, role=? WHERE id=?",
                      (nama, username, password, role, user_id))
                else:
                    c.execute("UPDATE users SET nama=?, username=?, role=? WHERE id=?",
                      (nama, username, role, user_id))
            else:  # insert
                password = generate_password_hash(password)
                c.execute("INSERT INTO users (nama, username, password, role) VALUES (?, ?, ?, ?)",
                  (nama, username, password, role))
            conn.commit()
            conn.close()
            return redirect('/users')

    conn.close()
    return render_template('user_form.html', user=user)

@app.route('/users/delete/<int:user_id>')
def delete_user(user_id):
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect('/login')
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()
    conn.close()
    return redirect('/users')

if __name__ == '__main__':
    init_db()
    app.run(debug=True)