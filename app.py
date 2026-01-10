import json
import os
from flask import Flask, render_template

app = Flask(__name__)

def load_data(filename):
    filepath = os.path.join('data', filename)
    with open(filepath, 'r') as f:
        return json.load(f)

@app.route('/')
def index():
    about_data = load_data('about.json')
    return render_template('index.html', title='Home', about=about_data)

@app.route('/publications')
def publications():
    publications_data = load_data('publications.json')
    return render_template('publications.html', title='Publications', publications=publications_data)

@app.route('/books')
def books():
    books_data = load_data('books.json')
    return render_template('books.html', title='Books', books=books_data)

@app.route('/code')
def code():
    code_data = load_data('code.json')
    return render_template('code.html', title='Code', code=code_data)

@app.route('/data')
def data():
    data_data = load_data('data.json')
    return render_template('data.html', title='Data', data=data_data)

@app.route('/news')
def news():
    news_data = load_data('news.json')
    return render_template('news.html', title='News', news=news_data)

@app.route('/awards')
def awards():
    awards_data = load_data('awards.json')
    return render_template('awards.html', title='Awards', awards=awards_data)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
