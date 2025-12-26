import os
import sqlite3
from datetime import datetime
from flask import Flask, jsonify, render_template, request, send_from_directory, url_for
from werkzeug.utils import secure_filename

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, 'lostfound.db')
UPLOAD_DIR = os.path.join(BASE_DIR, 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_DIR
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB

os.makedirs(UPLOAD_DIR, exist_ok=True)


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        '''CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            category TEXT NOT NULL,
            color TEXT NOT NULL,
            location TEXT,
            image_path TEXT,
            author_id TEXT,
            created_at TEXT NOT NULL
        )'''
    )
    conn.commit()
    conn.close()


def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


@app.route('/api/posts', methods=['GET'])
def list_posts():
    category = request.args.get('category')
    color = request.args.get('color')

    query = 'SELECT * FROM posts'
    params = []
    conditions = []

    if category and category != 'all':
        conditions.append('category = ?')
        params.append(category)
    if color and color != 'all':
        conditions.append('color = ?')
        params.append(color)

    if conditions:
        query += ' WHERE ' + ' AND '.join(conditions)

    query += ' ORDER BY id DESC'

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(query, params).fetchall()
    conn.close()

    def to_dict(row):
        image_url = url_for('uploaded_file', filename=row['image_path']) if row['image_path'] else None
        return {
            'id': row['id'],
            'title': row['title'],
            'content': row['content'],
            'category': row['category'],
            'color': row['color'],
            'location': row['location'],
            'image': image_url,
            'date': row['created_at'],
            'authorId': row['author_id'],
        }

    return jsonify([to_dict(r) for r in rows])


@app.route('/api/posts', methods=['POST'])
def create_post():
    if 'title' not in request.form or 'content' not in request.form:
        return jsonify({'error': '제목과 내용을 입력해주세요'}), 400

    title = request.form['title'].strip()
    content = request.form['content'].strip()
    category = request.form.get('category', '기타')
    color = request.form.get('color', '기타')
    location = request.form.get('location') or ''
    author_id = request.form.get('authorId')

    if not title or not content:
        return jsonify({'error': '제목과 내용을 입력해주세요'}), 400

    filename_on_disk = None
    file = request.files.get('image')
    if file and file.filename:
        if not allowed_file(file.filename):
            return jsonify({'error': '지원하지 않는 파일 형식입니다.'}), 400
        safe_name = secure_filename(file.filename)
        timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S%f')
        filename_on_disk = f"{timestamp}_{safe_name}"
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename_on_disk))

    created_at = datetime.now().strftime('%Y-%m-%d %H:%M')

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        'INSERT INTO posts (title, content, category, color, location, image_path, author_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
        (title, content, category, color, location, filename_on_disk, author_id, created_at),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()

    image_url = url_for('uploaded_file', filename=filename_on_disk) if filename_on_disk else None

    return jsonify({
        'id': new_id,
        'title': title,
        'content': content,
        'category': category,
        'color': color,
        'location': location,
        'image': image_url,
        'date': created_at,
        'authorId': author_id,
    }), 201


@app.route('/api/posts/<int:post_id>', methods=['DELETE'])
def delete_post(post_id):
    author_id = request.args.get('authorId')
    if not author_id:
        return jsonify({'error': 'authorId required'}), 400

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute('SELECT * FROM posts WHERE id = ?', (post_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'not found'}), 404

    if row['author_id'] != author_id:
        conn.close()
        return jsonify({'error': 'not allowed'}), 403

    if row['image_path']:
        try:
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], row['image_path']))
        except FileNotFoundError:
            pass

    conn.execute('DELETE FROM posts WHERE id = ?', (post_id,))
    conn.commit()
    conn.close()

    return jsonify({'ok': True})


init_db()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
