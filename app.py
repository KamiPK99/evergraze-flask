from flask import Flask, render_template, request, redirect, url_for, send_file
import sqlite3
import pandas as pd
import os
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor
from datetime import datetime

app = Flask(__name__)
DB_PATH = "cattle_farm.db"

def ensure_id_columns_exist():
    conn = connect_db()
    cursor = conn.cursor()

    tables = {
        "livestock": ["animal_id", "name", "breed", "age", "purchase_date", "source"],
        "weight_tracking": ["animal_id", "date", "weight", "notes"],
        "vaccinations": ["animal_id", "vaccine_name", "date_given", "next_due", "vet_name"]
    }

    for table, columns in tables.items():
        cursor.execute(f"PRAGMA table_info({table})")
        existing_columns = [col[1] for col in cursor.fetchall()]
        if "id" not in existing_columns:
            temp_cols = ", ".join([f"{col} TEXT" for col in columns])
            cursor.execute(f"""
                CREATE TABLE {table}_temp (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    {temp_cols}
                )
            """)
            col_names = ", ".join(columns)
            cursor.execute(f"""
                INSERT INTO {table}_temp ({col_names})
                SELECT {col_names} FROM {table}
            """)
            cursor.execute(f"DROP TABLE {table}")
            cursor.execute(f"ALTER TABLE {table}_temp RENAME TO {table}")
            conn.commit()
    conn.close()


def connect_db():
    return sqlite3.connect(DB_PATH)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/livestock', methods=['GET', 'POST'])
def livestock():
    conn = connect_db()
    cursor = conn.cursor()
    if request.method == 'POST':
        data = (request.form['animal_id'], request.form['name'], request.form['breed'], request.form['age'], request.form['purchase_date'], request.form['source'])
        cursor.execute("INSERT INTO livestock (animal_id, name, breed, age, purchase_date, source) VALUES (?, ?, ?, ?, ?, ?)", data)
        conn.commit()
    cursor.execute("SELECT * FROM livestock ORDER BY id DESC LIMIT 10")
    records = cursor.fetchall()
    conn.close()
    return render_template('livestock.html', records=records)

@app.route('/weight', methods=['GET', 'POST'])
def weight():
    conn = connect_db()
    cursor = conn.cursor()
    if request.method == 'POST':
        data = (request.form['animal_id'], request.form['date'], request.form['weight'], request.form['notes'])
        cursor.execute("INSERT INTO weight_tracking (animal_id, date, weight, notes) VALUES (?, ?, ?, ?)", data)
        conn.commit()
    cursor.execute("SELECT * FROM weight_tracking ORDER BY id DESC LIMIT 10")
    records = cursor.fetchall()
    conn.close()
    return render_template('weight.html', records=records)

@app.route('/vaccination', methods=['GET', 'POST'])
def vaccination():
    conn = connect_db()
    cursor = conn.cursor()
    if request.method == 'POST':
        data = (request.form['animal_id'], request.form['vaccine_name'], request.form['date_given'], request.form['next_due'], request.form['vet_name'])
        cursor.execute("INSERT INTO vaccinations (animal_id, vaccine_name, date_given, next_due, vet_name) VALUES (?, ?, ?, ?, ?)", data)
        conn.commit()
    cursor.execute("SELECT * FROM vaccinations ORDER BY id DESC LIMIT 10")
    records = cursor.fetchall()
    conn.close()
    return render_template('vaccination.html', records=records)

@app.route('/manage')
def manage():
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM livestock")
    livestock = cursor.fetchall()
    cursor.execute("SELECT * FROM weight_tracking")
    weights = cursor.fetchall()
    cursor.execute("SELECT * FROM vaccinations")
    vaccines = cursor.fetchall()
    conn.close()
    return render_template('manage.html', livestock=livestock, weights=weights, vaccines=vaccines)

@app.route('/delete/<table>/<int:record_id>', methods=['POST'])
def delete_record(table, record_id):
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute(f"DELETE FROM {table} WHERE id = ?", (record_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('manage'))

@app.route('/edit/<table>/<int:record_id>', methods=['GET', 'POST'])
def edit_record(table, record_id):
    conn = connect_db()
    cursor = conn.cursor()
    if request.method == 'POST':
        form_data = request.form.to_dict()
        columns = ', '.join(f"{key} = ?" for key in form_data.keys())
        values = list(form_data.values())
        values.append(record_id)
        cursor.execute(f"UPDATE {table} SET {columns} WHERE id = ?", values)
        conn.commit()
        conn.close()
        return redirect(url_for('manage'))
    else:
        cursor.execute(f"SELECT * FROM {table} WHERE id = ?", (record_id,))
        record = cursor.fetchone()
        col_names = [description[0] for description in cursor.description]
        conn.close()
        return render_template('edit.html', table=table, record=record, columns=col_names)

@app.route("/export_select", methods=["GET", "POST"])
def export_select():
    if request.method == "POST":
        animal_id = request.form.get("animal_id")
        export_type = request.form.get("export_type")
        if export_type == "pdf":
            return redirect(url_for("export_pdf", animal_id=animal_id))
        elif export_type == "excel":
            return redirect(url_for("export_excel_for_animal", animal_id=animal_id))
    return render_template("export.html")

@app.route("/export/excel/<animal_id>")
def export_excel_for_animal(animal_id):
    conn = connect_db()
    livestock = pd.read_sql_query(f"SELECT * FROM livestock WHERE animal_id = '{animal_id}'", conn)
    weight = pd.read_sql_query(f"SELECT * FROM weight_tracking WHERE animal_id = '{animal_id}'", conn)
    vaccine = pd.read_sql_query(f"SELECT * FROM vaccinations WHERE animal_id = '{animal_id}'", conn)
    conn.close()

    file_path = f"static/evergraze_export_{animal_id}.xlsx"
    with pd.ExcelWriter(file_path) as writer:
        livestock.to_excel(writer, sheet_name='Livestock', index=False)
        weight.to_excel(writer, sheet_name='WeightTracking', index=False)
        vaccine.to_excel(writer, sheet_name='Vaccinations', index=False)
    return send_file(file_path, as_attachment=True)


def export_beautiful_pdf(animal_id):
    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM livestock WHERE animal_id = ?", (animal_id,))
    livestock = cursor.fetchone()
    cursor.execute("SELECT * FROM weight_tracking WHERE animal_id = ?", (animal_id,))
    weights = cursor.fetchall()
    cursor.execute("SELECT * FROM vaccinations WHERE animal_id = ?", (animal_id,))
    vaccines = cursor.fetchall()
    conn.close()

    if not livestock:
        return None

    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import inch
    from reportlab.lib.colors import HexColor

    columns = ['Animal ID', 'Name', 'Breed', 'Age', 'Purchase Date', 'Source']
    pdf_path = f"static/evergraze_report_{animal_id}.pdf"
    c = canvas.Canvas(pdf_path, pagesize=A4)
    width, height = A4
    y = height - inch

    # Background
    c.setFillColor(HexColor("#fdfbf6"))
    c.rect(0, 0, width, height, fill=1)
    c.setFillColorRGB(0, 0, 0)

    # Logo
    logo_path = "static/logo.png"
    if os.path.exists(logo_path):
        c.drawImage(logo_path, width/2 - inch, y - 50, width=2 * inch, height=1 * inch, preserveAspectRatio=True, mask='auto')

    # Title
    c.setFont("Helvetica-Bold", 25)
    c.drawCentredString(width / 2, y - 80, "EverGraze Farms")
    c.setFont("Helvetica", 15)
    c.drawCentredString(width / 2, y - 95, "Livestock Health & History Certificate")

    y -= 120

    # --- Animal Profile Section ---
    c.setFont("Helvetica-Bold", 12)
    c.setStrokeColorRGB(0.2, 0.2, 0.2)
    c.rect(inch * 0.4, y, width - inch * 0.8, 20, stroke=1, fill=0)
    c.drawString(inch * 0.5, y + 5, "Animal Profile")
    y -= 20

    c.setFont("Helvetica", 10)
    for label, val in zip(columns, livestock):
        c.drawString(inch * 0.6, y, f"{label}: {val}")
        y -= 15

    y -= 15

    # --- Weight Tracking Section ---
    c.setFont("Helvetica-Bold", 12)
    c.rect(inch * 0.4, y, width - inch * 0.8, 20, stroke=1, fill=0)
    c.drawString(inch * 0.5, y + 5, "Weight Tracking")
    y -= 15

    c.setFont("Helvetica", 10)
    for w in weights:
        c.drawString(inch * 0.6, y, f"Date: {w[2]}  |  Weight: {w[3]} kg  |  Notes: {w[4]}")
        y -= 15

    y -= 15

    # --- Vaccination Section ---
    c.setFont("Helvetica-Bold", 12)
    c.rect(inch * 0.4, y, width - inch * 0.8, 20, stroke=1, fill=0)
    c.drawString(inch * 0.5, y + 5, "Vaccination Records")
    y -= 15

    c.setFont("Helvetica", 10)
    for v in vaccines:
        c.drawString(inch * 0.6, y, f"Vaccine: {v[2]}  |  Given: {v[3]}  |  Next Due: {v[4]}  |  Vet: {v[5]}")
        y -= 15

    # Footer
    c.setFont("Helvetica-Oblique", 8)
    c.drawString(inch * 0.5, inch * 0.5, f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M')} | EverGraze Farms")

    c.save()
    return pdf_path

@app.route("/export/pdf/<animal_id>")
def export_pdf(animal_id):
    pdf_path = export_beautiful_pdf(animal_id)
    if pdf_path:
        return send_file(pdf_path, as_attachment=True)
    return "Animal not found", 404

 
if __name__ == '__main__':
    ensure_id_columns_exist()
    app.run(debug=True)