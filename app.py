import json
import os
from flask import Flask, render_template

app = Flask(__name__)


def load_data(filename):
    filepath = os.path.join('data', filename)
    with open(filepath, 'r') as f:
        return json.load(f)

def load_data_from_folder(folder_path):
    data_list = []
    full_path = os.path.join('data', folder_path)
    if not os.path.exists(full_path):
        return []
        
    for filename in sorted(os.listdir(full_path)): # Sort for consistent order
        if filename.endswith('.json'):
            filepath = os.path.join(full_path, filename)
            with open(filepath, 'r') as f:
                data_list.append(json.load(f))
    return data_list

@app.route('/')
def index():
    about_data = load_data('about.json')
    return render_template('index.html', title='Home', about=about_data)

@app.route('/publications')
def publications():
    publications_data = load_data_from_folder('publications')
    publications_data.sort(key=lambda x: int(x.get('year', 0)), reverse=True)
    return render_template('publications.html', title='Publications', publications=publications_data)

@app.route('/books')
def books():
    books_data = load_data_from_folder('books')
    return render_template('books.html', title='Books', books=books_data)

@app.route('/code')
def code():
    code_data = {
        'r': load_data_from_folder('code/r'),
        'python': load_data_from_folder('code/python'),
        'matlab': load_data_from_folder('code/matlab')
    }
    return render_template('code.html', title='Code', code=code_data)

@app.route('/data')
def data():
    data_data = load_data_from_folder('datasets')
    return render_template('data.html', title='Data', data=data_data)

@app.route('/news')
def news():
    news_data = load_data_from_folder('news')
    return render_template('news.html', title='News', news=news_data)

@app.route('/awards')
def awards():
    awards_data = load_data_from_folder('awards')
    return render_template('awards.html', title='Awards', awards=awards_data)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
