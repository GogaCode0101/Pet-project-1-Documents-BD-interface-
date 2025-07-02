from flask import Flask, render_template, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text, inspect
import os

app = Flask(__name__)

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:12321@localhost/sql21'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/documents')
def documents():
    # Группировка документов по категориям
    document_categories = {
        'Договоры': [
            'договоры_оказания_услуг',
            'договоры_подряда',
            'договоры_подряда_физлиц',
            'договоры_социального_найма',
            'дополнительные_соглашения_подряд'
        ],
        'Акты': [
            'акты_выполненных_работ_допсоглаше',
            'акты_выполненных_работ_физлиц',
            'акты_дополнительных_работ',
            'акты_оказания_услуг',
            'акты_приема_передачи_материалов',
            'акты_сдачи_приемки_работ'
        ],
        'Другие': [
            'протоколы_распределения_вознагра'
        ]
    }
    return render_template('documents.html', categories=document_categories)

@app.route('/reference')
def reference():
    # List of reference tables
    reference_tables = [
        'города',
        'лица',
        'материалы',
        'предметы',
        'регионы',
        'улицы'
    ]
    return render_template('reference.html', tables=reference_tables)

@app.route('/queries')
def queries():
    return render_template('queries.html')

@app.route('/api/table/<table_name>')
def get_table_data(table_name):
    try:
        # Специальные запросы для справочных таблиц с JOIN
        if table_name == 'города':
            query = text('''
                SELECT г.id, р.название as регион, г.название
                FROM города г
                JOIN регионы р ON г.регион_id = р.id
            ''')
        elif table_name == 'улицы':
            query = text('''
                SELECT у.id, г.название as город, у.название
                FROM улицы у
                JOIN города г ON у.город_id = г.id
            ''')
        elif table_name == 'предметы':
            query = text('''
                SELECT п.id, у.название as улица, п.дом, п.квартира, п.площадь, п.назначение
                FROM предметы п
                JOIN улицы у ON п.улица_id = у.id
            ''')
        else:
            # Для остальных таблиц используем обычный SELECT
            query = text(f'SELECT * FROM "{table_name}"')
        
        result = db.session.execute(query)
        columns = result.keys()
        data = []
        for row in result:
            row_dict = dict(zip(columns, row))
            # Специальная обработка для таблицы договоры_социального_найма
            if table_name == 'договоры_социального_найма' and 'срок' in row_dict:
                val = row_dict['срок']
                if val is not None:
                    # timedelta -> строка (например, '60 months' или '5 years')
                    row_dict['срок'] = str(val)
            data.append(row_dict)
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/table_structure/<table_name>')
def get_table_structure(table_name):
    try:
        inspector = inspect(db.engine)
        columns = inspector.get_columns(table_name)
        structure = [{'name': col['name'], 'type': str(col['type'])} for col in columns]
        return jsonify({'success': True, 'structure': structure})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/add_record/<table_name>', methods=['POST'])
def add_record(table_name):
    try:
        data = request.json
        
        # Специальная обработка для таблицы города
        if table_name == 'города':
            region_id = data.get('регион_id')
            city_name = data.get('название')
            
            if not region_id or not city_name:
                return jsonify({'success': False, 'error': 'Необходимо указать регион и название города'})
            
            query = text(f'INSERT INTO "{table_name}" (регион_id, название) VALUES ({region_id}, \'{city_name}\') RETURNING *')
        
        # Специальная обработка для таблицы улицы
        elif table_name == 'улицы':
            city_id = data.get('город_id')
            street_name = data.get('название')
            
            if not city_id or not street_name:
                return jsonify({'success': False, 'error': 'Необходимо указать город и название улицы'})
            
            query = text(f'INSERT INTO "{table_name}" (город_id, название) VALUES ({city_id}, \'{street_name}\') RETURNING *')
        
        # Обычная обработка для остальных таблиц
        else:
            columns = ', '.join([f'"{k}"' for k in data.keys()])
            values = ', '.join([f"'{v}'" for v in data.values()])
            query = text(f'INSERT INTO "{table_name}" ({columns}) VALUES ({values}) RETURNING *')
        
        result = db.session.execute(query)
        db.session.commit()
        return jsonify({'success': True, 'data': dict(zip(result.keys(), result.fetchone()))})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/update_record/<table_name>', methods=['POST'])
def update_record(table_name):
    try:
        data = request.json
        # Получаем первичный ключ таблицы
        inspector = inspect(db.engine)
        pk = inspector.get_pk_constraint(table_name)['constrained_columns'][0]
        
        # Формируем SET часть запроса
        set_clause = ', '.join([f'"{k}" = \'{v}\'' for k, v in data.items() if k != pk])
        
        query = text(f'UPDATE "{table_name}" SET {set_clause} WHERE "{pk}" = \'{data[pk]}\' RETURNING *')
        result = db.session.execute(query)
        db.session.commit()
        return jsonify({'success': True, 'data': dict(zip(result.keys(), result.fetchone()))})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/execute_query', methods=['POST'])
def execute_query():
    try:
        query_text = request.json.get('query')
        if not query_text:
            return jsonify({'success': False, 'error': 'No query provided'})
        
        query = text(query_text)
        result = db.session.execute(query)
        columns = result.keys()
        data = [dict(zip(columns, row)) for row in result]
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

if __name__ == '__main__':
    app.run(debug=True) 