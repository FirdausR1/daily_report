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

# Pastikan kolom tambahan ada
def migrate_db():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    # Buat tabel utama jika belum ada
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nama TEXT, username TEXT UNIQUE,
            password TEXT, role TEXT)
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS laporan (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_user INTEGER, hari TEXT, tanggal TEXT,
            uraian TEXT, jenis_pekerjaan TEXT, equipment TEXT,
            status TEXT, keterangan TEXT, catatan TEXT,
            validasi TEXT DEFAULT 'Menunggu',
            validator TEXT, waktu_validasi TEXT,
            FOREIGN KEY(id_user) REFERENCES users(id))
    ''')
    # Tambah kolom jika model sudah ada
    cols = [r[1] for r in c.execute("PRAGMA table_info(laporan)")]
    for col in ['validasi','validator','waktu_validasi']:
        if col not in cols:
            c.execute(f"ALTER TABLE laporan ADD COLUMN {col} TEXT")
    # Tambah akun admin default
    c.execute("SELECT * FROM users WHERE username='admin'")
    if not c.fetchone():
        c.execute("INSERT INTO users (nama,username,password,role) VALUES (?,?,?,?)",
                  ('Admin','admin', generate_password_hash('admin123'), 'admin'))
    conn.commit(); conn.close()

migrate_db()

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method=='POST':
        u,p = request.form['username'], request.form['password']
        conn=sqlite3.connect(DATABASE); c=conn.cursor()
        c.execute("SELECT * FROM users WHERE username=?", (u,))
        user=c.fetchone(); conn.close()
        if user and check_password_hash(user[3], p):
            session['user_id'], session['username'], session['role'] = user[0], user[2], user[4]
            return redirect('/')
        return render_template('login.html', error="Login gagal")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

@app.route('/')
def index():
    if 'user_id' not in session: return redirect('/login')
    role, usr = session['role'], session['username']
    conn=sqlite3.connect(DATABASE); c=conn.cursor()
    c.execute("SELECT COUNT(*) FROM laporan WHERE validasi='Tervalidasi'")
    total_laporan=c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM users"); total_user=c.fetchone()[0]
    c.execute("SELECT jenis_pekerjaan,COUNT(*) FROM laporan WHERE validasi='Tervalidasi' GROUP BY jenis_pekerjaan")
    ringkasan=c.fetchall(); conn.close()
    return render_template('index.html',
        username=usr, role=role,
        total_laporan=total_laporan,
        total_user=total_user,
        ringkasan=ringkasan)

@app.route('/input', methods=['GET','POST'])
def input_laporan():
    if 'user_id' not in session or session['role'] not in ['admin','teknisi']:
        return redirect('/login')
    if request.method=='POST':
        data=(
            session['user_id'], request.form['hari'], request.form['tanggal'],
            request.form['uraian'], request.form['jenis'],
            request.form['equipment'], request.form['status'],
            request.form['keterangan'], request.form['catatan']
        )
        conn=sqlite3.connect(DATABASE); c=conn.cursor()
        c.execute("""INSERT INTO laporan
            (id_user,hari,tanggal,uraian,jenis_pekerjaan,
            equipment,status,keterangan,catatan)
            VALUES (?,?,?,?,?,?,?,?,?)""", data)
        conn.commit(); conn.close()
        return redirect('/laporan')
    return render_template('input.html')

@app.route('/laporan')
def lihat_laporan():
    if 'user_id' not in session: return redirect('/login')
    f_t, f_j = request.args.get('tanggal',''), request.args.get('jenis','')
    conn=sqlite3.connect(DATABASE); c=conn.cursor()
    base = """SELECT l.id,l.tanggal,l.hari,l.jenis_pekerjaan,
        l.equipment,l.status,l.keterangan,l.catatan,
        u.nama,l.validasi,l.validator,l.waktu_validasi
        FROM laporan l JOIN users u ON l.id_user=u.id
        WHERE 1=1"""
    params=[]
    if session['role']!='supervisor':
        base += " AND l.validasi='Tervalidasi'"
    if f_t:
        base += " AND l.tanggal=?"; params.append(f_t)
    if f_j:
        base += " AND l.jenis_pekerjaan LIKE ?"; params.append('%'+f_j+'%')
    base += " ORDER BY l.tanggal DESC"
    c.execute(base, params); rows=c.fetchall(); conn.close()
    return render_template('laporan.html', laporan=rows,
                           filter_tanggal=f_t, filter_jenis=f_j)

@app.route('/laporan/validasi/<int:laporan_id>')
def validasi_laporan(laporan_id):
    if session.get('role')!='supervisor': return redirect('/login')
    conn=sqlite3.connect(DATABASE); c=conn.cursor()
    now=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("""UPDATE laporan SET validasi='Tervalidasi',
        validator=?, waktu_validasi=? WHERE id=?""",
        (session['username'], now, laporan_id))
    conn.commit(); conn.close()
    return redirect('/laporan')

@app.route('/laporan/batal_validasi/<int:laporan_id>')
def batal_validasi(laporan_id):
    if session.get('role')!='supervisor': return redirect('/login')
    conn=sqlite3.connect(DATABASE); c=conn.cursor()
    c.execute("""UPDATE laporan SET validasi='Menunggu',
        validator=NULL, waktu_validasi=NULL WHERE id=?""",
        (laporan_id,))
    conn.commit(); conn.close()
    return redirect('/laporan')

@app.route('/export-excel')
def export_excel():
    if 'user_id' not in session: return redirect('/login')
    conn=sqlite3.connect(DATABASE); c=conn.cursor()
    c.execute("""SELECT tanggal,hari,jenis_pekerjaan,equipment,
        status,keterangan,catatan,u.nama
        FROM laporan l JOIN users u ON l.id_user=u.id
        WHERE validasi='Tervalidasi'
        ORDER BY tanggal DESC""")
    data=c.fetchall(); conn.close()
    wb=openpyxl.Workbook(); ws=wb.active; ws.title='Laporan Maintenance'
    ws.append(['Tanggal','Hari','Jenis Pekerjaan','Equipment','Status','Keterangan','Catatan','Teknisi'])
    for row in data: ws.append(row)
    out=BytesIO(); wb.save(out); out.seek(0)
    return send_file(out, download_name="laporan.xlsx", as_attachment=True)

# User management
@app.route('/users')
def users():
    if session.get('role')!='admin': return redirect('/login')
    conn=sqlite3.connect(DATABASE); c=conn.cursor()
    c.execute("SELECT * FROM users"); us=c.fetchall(); conn.close()
    return render_template('users.html', users=us)

@app.route('/users/add', methods=['GET','POST'])
@app.route('/users/edit/<int:uid>', methods=['GET','POST'])
def add_edit_user(uid=None):
    if session.get('role')!='admin': return redirect('/login')
    conn=sqlite3.connect(DATABASE); c=conn.cursor()
    user=None
    if uid:
        c.execute("SELECT * FROM users WHERE id=?", (uid,)); user=c.fetchone()
    if request.method=='POST':
        n,u,role_req,p = request.form['nama'], request.form['username'], request.form['role'], request.form['password']
        # Cek duplikat
        if uid:
            c.execute("SELECT * FROM users WHERE username=? AND id!=?",(u,uid))
        else:
            c.execute("SELECT * FROM users WHERE username=?", (u,))
        if c.fetchone():
            conn.close()
            return render_template('user_form.html', user=user, error="Username sudah ada")
        if uid:
            if p:
                p_h=generate_password_hash(p)
                c.execute("UPDATE users SET nama=?,username=?,password=?,role=? WHERE id=?",
                          (n,u,p_h,role_req,uid))
            else:
                c.execute("UPDATE users SET nama=?,username=?,role=? WHERE id=?",
                          (n,u,role_req,uid))
        else:
            p_h=generate_password_hash(p)
            c.execute("INSERT INTO users(nama,username,password,role) VALUES(?,?,?,?)",
                      (n,u,p_h,role_req))
        conn.commit(); conn.close()
        return redirect('/users')
    conn.close()
    return render_template('user_form.html', user=user)

@app.route('/users/delete/<int:uid>')
def delete_user(uid):
    if session.get('role')!='admin': return redirect('/login')
    conn=sqlite3.connect(DATABASE); c=conn.cursor()
    c.execute("DELETE FROM users WHERE id=?", (uid,)); conn.commit(); conn.close()
    return redirect('/users')

if __name__=='__main__':
    app.run(debug=True)
