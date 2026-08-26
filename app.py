import json
import os
from flask import Flask, render_template, send_from_directory, make_response, url_for
import datetime 
import subprocess
import urllib.request
import urllib.error

app = Flask(__name__)

BOOKS_FOLDER = os.path.join(os.getcwd(), 'books_rendered') 
SLIDES_FOLDER = os.path.join(os.getcwd(), 'data', 'slides') 

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
                item = json.load(f)
                item['filename_stem'] = filename[:-5]
                data_list.append(item)
    return data_list

@app.route('/')
def index():
    about_data = load_data('about.json')
    return render_template('index.html', title='Home', about=about_data, description="Academic website of Marcelo S. Perlin, featuring publications, books, code, and data related to finance and data science.")

@app.context_processor
def inject_now():
    return {'year': datetime.datetime.now().year}

@app.route('/books/<book_name>/')
@app.route('/books/<book_name>/<path:path>')
def serve_book(book_name, path='index.html'):
    # Check if book exists
    full_book_path = os.path.join(BOOKS_FOLDER, book_name)
    if not os.path.exists(full_book_path) or not os.path.isdir(full_book_path):
        return "Book not found", 404
    
    return send_from_directory(full_book_path, path)


@app.route('/publications')
def publications():
    publications_data = load_data_from_folder('publications')
    publications_data.sort(key=lambda x: int(x.get('year', 0)), reverse=True)

    total_publications = len(publications_data)
    
    # publications with IF
    publications_with_if = [pub for pub in publications_data if pub.get('impact_factor')]
    total_publications_with_if = len(publications_with_if)

    # average if
    total_if = 0
    for pub in publications_with_if:
        total_if += float(pub.get('impact_factor', 0))
    
    avg_if = total_if / total_publications_with_if
    avg_if = round(avg_if, 2)
    
    # restrict size of abstract to 200 characters
    for publication in publications_data:
        publication['abstract'] = publication['abstract'][:400] + " ... (continued, check link for full abstract)"

    # add gscholar stats
    gscholar_stats = load_data('stats/gscholar.json')

    return render_template(
        'publications.html', 
        title='Publications', 
        publications=publications_data, 
        total_publications=total_publications, 
        total_publications_with_if=total_publications_with_if,
        avg_if=avg_if,
        gscholar_stats = gscholar_stats,
        description="Academic publications by Marcelo S. Perlin in finance and data science.")

@app.route('/books')
def books():
    books_data = load_data_from_folder('books')
    
    # Load Amazon stats if available
    try:
        amazon_stats = load_data('stats/amazon_books.json')
        books_stats = amazon_stats.get('books', {})
    except Exception:
        books_stats = {}
        
    for book in books_data:
        stem = book.get('filename_stem')
        if stem and stem in books_stats:
            book['amazon_rating'] = books_stats[stem].get('rating')
            book['amazon_ratings_count'] = books_stats[stem].get('ratings_count')
            
    books_data.sort(key=lambda x: (int(x.get('amazon_ratings_count', 0)), int(x.get('year', 0))), reverse=True)

    n_books = len(books_data)

    return render_template('books.html', title='Books', books=books_data, n_books=n_books, description="Books authored by Marcelo S. Perlin on financial data analysis, R, and Python.")

@app.route('/code/r')
def code_r():
    code_data_r = load_data_from_folder('code/r')
    
    # Sort R packages by number of downloads (descending)
    code_data_r.sort(key=lambda x: int(x.get('number_of_downloads', 0)), reverse=True)
    
    return render_template('code_r.html', title='Code (R)', code_r=code_data_r, description="Open source code and repositories in R.")

@app.route('/code/python')
def code_python():
    code_data_python = load_data_from_folder('code/python')
    return render_template('code_python.html', title='Code (Python)', code_python=code_data_python, description="Open source code and repositories in Python.")

@app.route('/data')
def data():
    data_data = load_data_from_folder('datasets')
    return render_template('data.html', title='Data', data=data_data, description="Datasets and financial data resources available for download.")

@app.route('/news')
def news():
    news_data = load_data_from_folder('news')
    # Sort by date descending
    news_data.sort(key=lambda x: x.get('date', ''), reverse=True)
    
    # Group news items by year while maintaining sorting
    grouped_news = {}
    for item in news_data:
        date_str = item.get('date', '')
        if date_str:
            year = date_str.split('-')[0]
        else:
            year = str(item.get('year', 'Unknown'))
        item['year'] = year
        if item.get('pdf'):
            item['pdf_url'] = url_for('serve_news_pdf', filename=os.path.basename(item['pdf']))
        if year not in grouped_news:
            grouped_news[year] = []
        grouped_news[year].append(item)
            
    return render_template('news.html', title='News', news=grouped_news, description="News coverage, interviews, and media appearances.")

@app.route('/awards')
def awards():
    awards_data = load_data_from_folder('awards')

    # sort by year
    awards_data.sort(key=lambda x: int(x.get('year', 0)), reverse=True)

    # Group awards by year while maintaining sorting
    grouped_awards = {}
    for award in awards_data:
        year = str(award.get('year', 'Unknown'))
        if year not in grouped_awards:
            grouped_awards[year] = []
        grouped_awards[year].append(award)

    return render_template('awards.html', title='Awards', awards=grouped_awards, description="Academic awards and honors received by Marcelo S. Perlin.")


@app.route('/consulting')
def consulting():
    consulting_data = load_data('consulting.json')
    return render_template('consulting.html', title='Consulting Services', content=consulting_data, description="Expert Financial Data Science Consulting by Marcelo S. Perlin. Services include R/Python programming, financial modeling, machine learning, and data visualization.")

@app.route('/slides')
def slides():
    slides_data = load_data_from_folder('slides')
    slides_data.sort(key=lambda x: str(x.get('date', x.get('year', ''))), reverse=True)
    return render_template('slides.html', title='Slides', slides=slides_data, description="Presentation slides, workshops, and research materials by Marcelo S. Perlin.")

@app.route('/slides/<slide_folder>/')
@app.route('/slides/<slide_folder>/<path:path>')
def serve_slide(slide_folder, path=None):
    slide_dir = os.path.join(SLIDES_FOLDER, slide_folder)
    if not os.path.exists(slide_dir) or not os.path.isdir(slide_dir):
        return "Slide presentation not found", 404
        
    if not path:
        # Check root folder first
        html_files = [f for f in os.listdir(slide_dir) if f.endswith('.html')]
        if 'index.html' in html_files:
            return send_from_directory(slide_dir, 'index.html')
        elif html_files:
            return send_from_directory(slide_dir, sorted(html_files)[0])
            
        # Check 'slides' subfolder
        slides_sub = os.path.join(slide_dir, 'slides')
        if os.path.exists(slides_sub) and os.path.isdir(slides_sub):
            sub_htmls = [f for f in os.listdir(slides_sub) if f.endswith('.html')]
            if 'index.html' in sub_htmls:
                return send_from_directory(slides_sub, 'index.html')
            elif sub_htmls:
                return send_from_directory(slides_sub, sorted(sub_htmls)[0])
        return "Presentation HTML not found", 404
            
    # If path directly exists in slide_dir
    full_path = os.path.join(slide_dir, path)
    if os.path.exists(full_path):
        return send_from_directory(slide_dir, path)
        
    # If path exists in slide_dir/slides
    sub_full_path = os.path.join(slide_dir, 'slides', path)
    if os.path.exists(sub_full_path):
        return send_from_directory(os.path.join(slide_dir, 'slides'), path)
        
    return "File not found", 404

@app.route('/site-log')
def site_log():
    # Git Commits
    try:
        git_log_output = subprocess.check_output(['git', 'log', '-n', '50', '--pretty=format:%h|%ar|%s']).decode('utf-8')
        commits = []
        for line in git_log_output.strip().split('\n'):
            if line:
                parts = line.split('|', 2)
                if len(parts) == 3:
                    commits.append({'hash': parts[0], 'date': parts[1], 'message': parts[2]})
    except Exception as e:
        commits = []
        
    # GitHub Actions
    actions = []
    try:
        url = "https://api.github.com/repos/msperlin/msperlin-flask-website/actions/runs?per_page=15"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            for run in data.get('workflow_runs', []):
                actions.append({
                    'name': run.get('name'),
                    'status': run.get('status'),
                    'conclusion': run.get('conclusion'),
                    'created_at': run.get('created_at', '')[:10],
                    'html_url': run.get('html_url')
                })
    except Exception as e:
        pass

    return render_template('site_log.html', title='Site Log', commits=commits, actions=actions, description="Website action logs and commit history.")

@app.route('/sitemap.xml')
def sitemap():
    """Generate sitemap.xml. Makes a list of urls and renders them."""
    pages = []
    ten_days_ago = (datetime.datetime.now() - datetime.timedelta(days=10)).date().isoformat()

    # static pages
    for rule in app.url_map.iter_rules():
        if "GET" in rule.methods and len(rule.arguments) == 0:
            pages.append(url_for(rule.endpoint, _external=True))

    # books
    for book_name in os.listdir(BOOKS_FOLDER):
        book_path = os.path.join(BOOKS_FOLDER, book_name)
        if os.path.isdir(book_path):
             # add main book page
             pages.append(url_for('serve_book', book_name=book_name, _external=True))
             
             # add subpages
             for root, dirs, files in os.walk(book_path):
                 for file in files:
                     if file.endswith('.html') and file != 'index.html': # index.html is already covered by serve_book
                         # Calculate relative path from book root
                         rel_path = os.path.relpath(os.path.join(root, file), book_path)
                         # Replace backslashes with forward slashes for URL consistency on Windows (though this is Linux)
                         rel_path = rel_path.replace('\\', '/')
                         pages.append(url_for('serve_book', book_name=book_name, path=rel_path, _external=True))

    # slides
    if os.path.exists(SLIDES_FOLDER):
        for slide_name in os.listdir(SLIDES_FOLDER):
            slide_path = os.path.join(SLIDES_FOLDER, slide_name)
            if os.path.isdir(slide_path):
                pages.append(url_for('serve_slide', slide_folder=slide_name, _external=True))

    sitemap_xml = render_template('sitemap.xml', pages=pages)
    response = make_response(sitemap_xml)
    response.headers["Content-Type"] = "application/xml"
    
    return response

@app.route('/news/pdfs/<path:filename>')
def serve_news_pdf(filename):
    pdf_folder = os.path.join(os.getcwd(), 'data', 'news', 'pdfs')
    return send_from_directory(pdf_folder, filename)

@app.route('/robots.txt')
def robots():
    return send_from_directory(app.static_folder, 'robots.txt')

@app.route('/f6d89283e4a24c25bcf682e06180dfd3.txt')
def indexnow_key():
    return send_from_directory(app.static_folder, 'f6d89283e4a24c25bcf682e06180dfd3.txt')

if __name__ == '__main__':
    app.run(debug=True, port=5000)

