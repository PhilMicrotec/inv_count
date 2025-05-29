# Copyright (c) 2025, Microtec and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document # type: ignore


class InventoryCount(Document):
	pass

import frappe
import pandas as pd
from io import StringIO
# Si vous lisez depuis SQL, vous pourriez avoir besoin de :
# import pymysql # ou psycopg2, sqlalchemy, etc.
# from sqlalchemy import create_engine # Pour une approche plus générique avec Pandas et SQL

@frappe.whitelist()
def import_data_with_pandas(parent_docname, data_source_type="csv", source_content=None):
    """
    Importe les données dans une child table d'un document Frappe en utilisant Pandas.

    :param parent_docname: Le nom (name) du document parent.
    :param data_source_type: Type de source ('csv', 'sql').
    :param source_content: Contenu CSV (str) ou dictionnaire de configuration SQL (dict).
    """
    try:
        parent_doc = frappe.get_doc("Votre_DocType_Parent", parent_docname)

        if not parent_doc:
            frappe.throw(f"Document parent '{parent_docname}' introuvable.")

        child_table_fieldname = "votre_champ_child_table" # Exemple: 'items'

        df = pd.DataFrame() # Initialiser un DataFrame vide

        if data_source_type == "csv":
            if not source_content:
                frappe.throw("Le contenu CSV est manquant.")
            csv_file = StringIO(source_content)
            df = pd.read_csv(csv_file)
        elif data_source_type == "sql":
            if not source_content or not isinstance(source_content, dict):
                frappe.throw("La configuration SQL est manquante ou invalide.")
            
            # Exemple pour MySQL avec SQLAlchemy (plus robuste)
            # engine = create_engine(f"mysql+pymysql://{source_content['user']}:{source_content['password']}@{source_content['host']}:{source_content['port']}/{source_content['database']}")
            # sql_query = source_content.get("query", "SELECT * FROM votre_table_externe")
            # df = pd.read_sql_query(sql_query, engine)

            # Exemple simplifié avec pymysql direct (sans SQLAlchemy)
            try:
                conn = pymysql.connect(**source_content)
                sql_query = source_content.get("query", "SELECT * FROM votre_table_externe")
                df = pd.read_sql_query(sql_query, conn)
                conn.close()
            except Exception as e:
                frappe.throw(f"Erreur de connexion ou de requête SQL: {e}")
        else:
            frappe.throw(f"Type de source de données non pris en charge: {data_source_type}")

        if df.empty:
            frappe.msgprint("Aucune donnée à importer après lecture de la source.")
            return

        # --- Étape de Nettoyage et de Transformation (très importante avec Pandas) ---
        # 1. Renommer les colonnes pour qu'elles correspondent aux noms de champs Frappe
        # C'est ici que vous feriez votre mappage entre la source et la destination Frappe.
        # Exemple: si votre CSV/SQL a 'Produit Code', vous voulez 'item_code' dans Frappe.
        df.rename(columns={
            "Product Code": "item_code",
            "Quantity": "qty",
            "Rate": "rate",
            "Description": "description"
            # Ajoutez tous vos mappages ici
        }, inplace=True)

        # 2. Convertir les types de données si nécessaire
        # Assurez-vous que les colonnes numériques sont bien des nombres.
        for col in ["qty", "rate"]: # Liste de vos colonnes numériques Frappe
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0) # 'coerce' met NaN pour les erreurs, fillna(0) remplace NaN par 0

        # 3. Supprimer les lignes avec des données non valides si nécessaire
        # df.dropna(subset=['item_code', 'qty'], inplace=True) # Ex: supprimer si item_code ou qty est manquant

        # 4. Sélectionner uniquement les colonnes pertinentes pour la child table
        # C'est une bonne pratique pour éviter d'insérer des colonnes inutiles.
        # Assurez-vous que tous les champs requis pour la child table sont présents.
        required_child_fields = ["item_code", "qty", "rate", "description"] # Adaptez à votre child table
        
        # Filtrez les colonnes du DataFrame pour ne garder que celles qui sont des champs Frappe valides
        # et qui sont nécessaires pour l'importation.
        df_to_import = df[[col for col in required_child_fields if col in df.columns]]

        # --- Fin de l'étape de Transformation ---

        # Effacer les éléments existants si vous voulez remplacer entièrement
        # parent_doc.set(child_table_fieldname, [])

        # Itérer sur les lignes du DataFrame et ajouter à la child table
        # .to_dict('records') est très efficace pour obtenir une liste de dictionnaires
        # où chaque dictionnaire est une ligne du DataFrame.
        for row_dict in df_to_import.to_dict('records'):
            # Chaque row_dict est un dictionnaire où les clés sont les noms de colonnes
            # (maintenant renommés pour correspondre aux champs Frappe)
            
            # Assurez-vous d'ajouter ici toute logique de validation Frappe spécifique
            # ou de récupération de dépendances (ex: vérifier si 'item_code' existe dans le DocType Item)
            
            parent_doc.append(child_table_fieldname, row_dict)

        parent_doc.save()
        frappe.db.commit()
        frappe.msgprint(f"Données importées avec succès dans la child table de '{parent_docname}' en utilisant Pandas.")

    except Exception as e:
        frappe.db.rollback()
        frappe.throw(f"Erreur lors de l'importation des données avec Pandas: {e}")