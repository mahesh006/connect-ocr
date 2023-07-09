from flask import Flask, render_template, request, session, redirect, jsonify
from werkzeug.utils import secure_filename
import os
import pyrebase
from flask import url_for
from azure.ai.formrecognizer import DocumentAnalysisClient
from azure.core.credentials import AzureKeyCredential
import pandas as pd 
from openpyxl import Workbook
import time
from Levenshtein import ratio




app = Flask(__name__)
app.secret_key = "secret_key"
app.config['UPLOAD_FOLDER'] = '/uploads'


# Configure your Firebase credentials
config = {    
 
}

firebase = pyrebase.initialize_app(config)
auth = firebase.auth()
storage = firebase.storage()
db = firebase.database()  



@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'email' in session:

        if request.method == 'POST':
            email = session['email']
            folder_name = request.form['folder_name']
            files = request.files.getlist('user_files')

        
            if len(files) == 0:
                return 'No files selected for uploading'

            
            uploads_dir = os.path.join(app.root_path, 'uploads')
            if not os.path.exists(uploads_dir):
                os.makedirs(uploads_dir)

            for file in files:
                if file.filename == '':
                    continue
                filename = secure_filename(file.filename)
                file_path = os.path.join(uploads_dir, filename)
                file.save(file_path)

                # Upload the file to Firebase Storage
                storage.child("{}/{}/{}".format(email, folder_name, filename)).put(file_path)

                # Get the download url and save it to Firestore
                url = storage.child("{}/{}/{}".format(email, folder_name, filename)).get_url(None)

                data = {"email": email, "folder_name": folder_name, "file_name": filename, "url": url}
                db.child("user_files").push(data)

                # Delete the local file
                os.remove(file_path)

            return redirect(url_for('dashboard'))  
        
        # Retrieve file metadata from Firestore
        all_files = db.child("user_files").order_by_child("email").equal_to(session['email']).get()

        # Organize files by folder name
        folders = {}
        for file in all_files.each():
            file_data = file.val()
            folder_name = file_data['folder_name']
            if folder_name not in folders:
                folders[folder_name] = []
            folders[folder_name].append({'name': file_data['file_name'], 'url': file_data['url']})

        return render_template('dashboard.html', email=session['email'], folders=folders)
    else:
        return redirect('/login')


@app.route('/delete_folder', methods=['POST'])
def delete_folder():
    if 'email' in session and 'user_token' in session:
        email = session['email']
        folder_name = request.form['folder_name']
        user_id_token = session['user_token'] 

        # Get all files in the folder
        all_files = db.child("user_files").order_by_child("email").equal_to(session['email']).get()
        files_to_delete = [file for file in all_files.each() if file.val()['folder_name'] == folder_name]



        for file in files_to_delete:
            # Delete from Firebase Storage
            storage.delete("{}/{}/{}".format(email, folder_name, file.val()['file_name']), user_id_token)

            # Delete from Firestore
            db.child("user_files").child(file.key()).remove()

        return 'Folder deleted successfully'

    return 'Operation not allowed'




@app.route('/')
def index():
    return render_template('index.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        try:
            user = auth.create_user_with_email_and_password(email, password)
            session['email'] = email
            return redirect('/dashboard')
        except Exception as e:
            error = str(e)
            return render_template('signup.html', error=error)
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        try:
            user = auth.sign_in_with_email_and_password(email, password)
            session['email'] = email
            session['user_token'] = user['idToken']  # Save the idToken into the session
            return redirect('/dashboard')
        except Exception as e:
            error = str(e)
            return render_template('login.html', error=error)
    return render_template('login.html')




@app.route('/logout')
def logout():
    session.pop('email', None)
    return redirect('/login')




@app.route('/analyze', methods=['POST'])
def analyze_images():
    requestData = request.get_json()
    images = requestData.get('images', [])
    language = requestData.get('language', 'en')
    todos = requestData.get('todos', [])
    model = requestData.get('model', '')


    language_mapping = {
        'English': 'en',
        'Spanish': 'es',
        'French': 'fr',
        'German': 'de',
        'Italian': 'it',
        'Dutch': 'nl',
        'Portuguese': 'pt',
        'Chinese Simplified': 'zh-Hans',
        'Chinese Traditional': 'zh-Hant',
        'Japanese': 'ja',
        'Korean': 'ko',
        'Russian': 'ru'
    }

    language_code = language_mapping.get(language, 'en')

    endpoint = ''
    key = ''

    print(model.lower())

    if model == 'Documents':
        document_analysis_client = DocumentAnalysisClient(endpoint, AzureKeyCredential(key), default_language=language_code)

        results = []
        df = pd.DataFrame()
        file_counter = 1

        for image_url in images:
            poller = document_analysis_client.begin_analyze_document_from_url("prebuilt-document", image_url)
            result = poller.result()

            image_results = {}
            for kv_pair in result.key_value_pairs:
                if kv_pair.key and kv_pair.value:
                    key = kv_pair.key.content
                    value = kv_pair.value.content
                    if key in todos or any(ratio(key.lower(), todo.lower()) >= 0.8 for todo in todos):
                        image_results[key] = value

            results.append({
                'image_url': image_url,
                'results': image_results,
                'raw_results': result.content  
            })

            data_dict = image_results

            if df.empty or set(df.columns) == set(data_dict.keys()):
                df = df.append(data_dict, ignore_index=True)
            else:
                
                timestamp = str(time.time()).replace(".", "")
                excel_filename = f'{timestamp}.xlsx'
                df.to_excel(excel_filename, index=False)

                storage.child("{}/{}/{}".format(session['email'], 'analysis_results', excel_filename)).put(excel_filename)
                url = storage.child("{}/{}/{}".format(session['email'], 'analysis_results', excel_filename)).get_url(None)
                data = {"email": session['email'], "folder_name": 'analysis_results', "file_name": excel_filename, "url": url, "uploaded_at": time.time()}
                db.child("analysis_results").push(data)

                file_counter += 1
                df = pd.DataFrame(data_dict, index=[0])
        
        if not df.empty:
            
            timestamp = str(time.time()).replace(".", "")
            excel_filename = f'{timestamp}.xlsx'
            df.to_excel(excel_filename, index=False)
            
            storage.child("{}/{}/{}".format(session['email'], 'analysis_results', excel_filename)).put(excel_filename)
            url = storage.child("{}/{}/{}".format(session['email'], 'analysis_results', excel_filename)).get_url(None)
            data = {"email": session['email'], "folder_name": 'analysis_results', "file_name": excel_filename, "url": url, "uploaded_at": time.time()}
            db.child("analysis_results").push(data)
            os.remove(excel_filename)

    
    else:
        document_analysis_client = DocumentAnalysisClient(endpoint, AzureKeyCredential(key))
        results = []

        for image_url in images:
            poller = document_analysis_client.begin_analyze_document_from_url("prebuilt-layout", image_url)
            result = poller.result()

            # Get tables
            for idx, table in enumerate(result.tables):
                table_data = []
                for cell in table.cells:
                    while len(table_data) <= cell.row_index:
                        table_data.append([])
                    while len(table_data[cell.row_index]) <= cell.column_index:
                        table_data[cell.row_index].append("")
                    table_data[cell.row_index][cell.column_index] = cell.content
                
                df = pd.DataFrame(table_data)
                timestamp = str(time.time()).replace(".", "")
                excel_filename = f'{timestamp}.xlsx'
                df.to_excel(excel_filename, index=False)

                storage.child("{}/{}/{}".format(session['email'], 'analysis_results', excel_filename)).put(excel_filename)
                url = storage.child("{}/{}/{}".format(session['email'], 'analysis_results', excel_filename)).get_url(None)
                data = {"email": session['email'], "folder_name": 'analysis_results', "file_name": excel_filename, "url": url, "uploaded_at": time.time()}
                db.child("analysis_results").push(data)
                os.remove(excel_filename)


                results.append({
                    'image_url': image_url,
                    'results': table_data,
                    'raw_results': result.content 
                })    

    return jsonify(results)


@app.route('/saved_files', methods=['GET'])
def saved_files():
    if 'email' in session:
        all_analysis_results = db.child("analysis_results").order_by_child("email").equal_to(session['email']).get()

        files = []
        for result in all_analysis_results.each():
            result_data = result.val()
            files.append({
                'id': result.key(),  # Firebase document ID
                'name': result_data['file_name'], 
                'url': result_data['url']
            })

        return render_template('saved_files.html', email=session['email'], files=files)
    else:
        return redirect('/login')



@app.route('/delete_analysis_result', methods=['POST'])
def delete_analysis_result():
    if 'email' in session and 'user_token' in session:
        email = session['email']
        file_name = request.form['file_name']  # The file name to delete
        user_id_token = session['user_token']

        # Get all analysis results for the email
        all_analysis_results = db.child("analysis_results").order_by_child("email").equal_to(email).get()
        analysis_result_to_delete = [result for result in all_analysis_results.each() if result.val()['file_name'] == file_name]

        if analysis_result_to_delete:
            result = analysis_result_to_delete[0]

            # Define the path based on your folder structure in Firebase Storage
            path = "{}/analysis_results/{}".format(email, file_name)

            # Delete from Firebase Storage
            storage.delete(path, user_id_token)

            # Delete from Firestore
            db.child("analysis_results").child(result.key()).remove()

            return redirect('/saved_files')
        
        else:
            return 'File not found'

    return redirect('/login')





@app.route('/folder_contents/<folder_name>', methods=['GET'])
def folder_contents(folder_name):
    # Retrieve file metadata from Firestore
    all_files = db.child("user_files").order_by_child("folder_name").equal_to(folder_name).get()

    # Organize files by folder name
    files = []
    for file in all_files.each():
        file_data = file.val()
        files.append({'name': file_data['file_name'], 'url': file_data['url']})

    return render_template('folder_contents.html', folder_name=folder_name, files=files)


if __name__ == '__main__':
    app.run(debug=True)