from flask import Blueprint, request, jsonify, current_app
import os
import pandas as pd
import numpy as np
from werkzeug.utils import secure_filename
from models import Dataset, db
from services.data_processor import DataProcessor
import logging
from datetime import datetime

data_bp = Blueprint('data', __name__, url_prefix='/api/data')

@data_bp.route('/upload', methods=['POST'])
def upload_file():
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'}), 400
        
        if file:
            filename = secure_filename(file.filename)
            upload_folder = current_app.config.get('UPLOAD_FOLDER', 'uploads')
            
            # Create upload folder if it doesn't exist
            os.makedirs(upload_folder, exist_ok=True)
            
            file_path = os.path.join(upload_folder, filename)
            file.save(file_path)
            
            # Process the file
            data_processor = DataProcessor()
            df = data_processor.parse_file(file_path, filename)
            
            if df is not None:
                # Create dataset record
                dataset = Dataset(
                    filename=filename,
                    file_path=file_path,
                    file_size=os.path.getsize(file_path),
                    num_rows=len(df),
                    num_columns=len(df.columns),
                    upload_timestamp=datetime.utcnow()
                )
                
                db.session.add(dataset)
                db.session.commit()
                
                return jsonify({
                    'success': True,
                    'dataset_id': dataset.id,
                    'filename': filename,
                    'rows': len(df),
                    'columns': len(df.columns)
                })
            else:
                return jsonify({'success': False, 'error': 'Failed to parse file'}), 400
                
    except Exception as e:
        current_app.logger.error(f"File upload error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@data_bp.route('/datasets', methods=['GET'])
def get_datasets():
    try:
        datasets = Dataset.query.all()
        dataset_list = []
        
        for dataset in datasets:
            dataset_list.append({
                'id': dataset.id,
                'filename': dataset.filename,
                'rows': dataset.num_rows,
                'columns': dataset.num_columns,
                'file_size': dataset.file_size,
                'created_at': dataset.upload_timestamp.isoformat() if dataset.upload_timestamp else None
            })
        
        return jsonify({
            'success': True,
            'datasets': dataset_list
        })
        
    except Exception as e:
        current_app.logger.error(f"Error fetching datasets: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@data_bp.route('/columns/<int:dataset_id>', methods=['GET'])
def get_columns(dataset_id):
    try:
        dataset = Dataset.query.get_or_404(dataset_id)
        data_processor = DataProcessor()
        
        df = data_processor.parse_file(dataset.file_path, dataset.filename)
        if df is None:
            return jsonify({'success': False, 'error': 'Failed to load dataset'}), 500
        
        columns = []
        for col in df.columns:
            col_info = {
                'name': col,
                'dtype': str(df[col].dtype),
                'is_numeric': pd.api.types.is_numeric_dtype(df[col]),
                'is_categorical': df[col].dtype == 'object',
                'is_datetime': pd.api.types.is_datetime64_any_dtype(df[col]),
                'null_count': int(df[col].isnull().sum()),
                'unique_count': int(df[col].nunique())
            }
            columns.append(col_info)
        
        return jsonify({
            'success': True,
            'columns': columns
        })
        
    except Exception as e:
        current_app.logger.error(f"Error fetching columns: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@data_bp.route('/column_stats/<int:dataset_id>/<column_name>', methods=['GET'])
def get_column_stats(dataset_id, column_name):
    try:
        dataset = Dataset.query.get_or_404(dataset_id)
        data_processor = DataProcessor()
        
        df = data_processor.parse_file(dataset.file_path, dataset.filename)
        if df is None:
            return jsonify({'success': False, 'error': 'Failed to load dataset'}), 500
        
        if column_name not in df.columns:
            return jsonify({'success': False, 'error': f'Column {column_name} not found'}), 404
        
        col = df[column_name]
        
        stats = {
            'non_null_count': int(col.count()),
            'null_count': int(col.isnull().sum()),
            'null_percentage': float(col.isnull().sum() / len(col) * 100),
            'unique_count': int(col.nunique()),
            'memory_usage': f"{col.memory_usage(deep=True) / 1024:.1f} KB"
        }
        
        return jsonify({
            'success': True,
            'stats': stats
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting column stats: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@data_bp.route('/value_counts/<int:dataset_id>/<column_name>', methods=['GET'])
def get_value_counts(dataset_id, column_name):
    try:
        dataset = Dataset.query.get_or_404(dataset_id)
        data_processor = DataProcessor()
        
        df = data_processor.parse_file(dataset.file_path, dataset.filename)
        if df is None:
            return jsonify({'success': False, 'error': 'Failed to load dataset'}), 500
        
        if column_name not in df.columns:
            return jsonify({'success': False, 'error': f'Column {column_name} not found'}), 404
        
        # Get top 20 value counts
        value_counts = df[column_name].value_counts().head(20).to_dict()
        
        # Convert to serializable format
        serializable_counts = {}
        for key, value in value_counts.items():
            serializable_counts[str(key)] = int(value)
        
        return jsonify({
            'success': True,
            'value_counts': serializable_counts
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting value counts: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@data_bp.route('/pattern_analysis/<int:dataset_id>/<column_name>', methods=['GET'])
def get_pattern_analysis(dataset_id, column_name):
    try:
        dataset = Dataset.query.get_or_404(dataset_id)
        data_processor = DataProcessor()
        
        df = data_processor.parse_file(dataset.file_path, dataset.filename)
        if df is None:
            return jsonify({'success': False, 'error': 'Failed to load dataset'}), 500
        
        if column_name not in df.columns:
            return jsonify({'success': False, 'error': f'Column {column_name} not found'}), 404
        
        col = df[column_name]
        
        analysis = {}
        
        if pd.api.types.is_numeric_dtype(col):
            # Numeric column analysis
            Q1 = col.quantile(0.25)
            Q3 = col.quantile(0.75)
            IQR = Q3 - Q1
            lower_bound = Q1 - 1.5 * IQR
            upper_bound = Q3 + 1.5 * IQR
            
            outliers = col[(col < lower_bound) | (col > upper_bound)]
            
            analysis = {
                'distribution_type': 'Numeric',
                'skewness': float(col.skew()) if col.count() > 0 else None,
                'outlier_count': len(outliers),
                'mean': float(col.mean()) if col.count() > 0 else None,
                'std': float(col.std()) if col.count() > 0 else None
            }
        else:
            # Categorical column analysis
            analysis = {
                'distribution_type': 'Categorical',
                'outlier_count': 0,
                'most_frequent': col.mode().iloc[0] if not col.mode().empty else None,
                'frequency_distribution': 'Even' if col.nunique() > len(col) * 0.8 else 'Skewed'
            }
        
        return jsonify({
            'success': True,
            **analysis
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting pattern analysis: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@data_bp.route('/preview/<int:dataset_id>', methods=['GET'])
def preview_dataset(dataset_id):
    try:
        dataset = Dataset.query.get_or_404(dataset_id)
        data_processor = DataProcessor()
        
        df = data_processor.parse_file(dataset.file_path, dataset.filename)
        if df is None:
            return jsonify({'success': False, 'error': 'Failed to load dataset'}), 500
        
        # Get first 10 rows
        preview_data = df.head(10).to_dict('records')
        
        return jsonify({
            'success': True,
            'data': preview_data,
            'columns': list(df.columns),
            'total_rows': len(df)
        })
        
    except Exception as e:
        current_app.logger.error(f"Error previewing dataset: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500