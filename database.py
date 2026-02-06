import sqlite3
from typing import List, Tuple, Optional


class Database:
    def __init__(self, db_name: str = "recipes.db"):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.cursor = self.conn.cursor()
        # 🔑 Включаем поддержку внешних ключей в SQLite
        self.cursor.execute("PRAGMA foreign_keys = ON")
        self._create_tables()

    def _create_tables(self):
        # Таблица пользователей
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                consent_given BOOLEAN DEFAULT FALSE,
                consent_date TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Таблица рецептов
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS recipes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                category TEXT CHECK(category IN ('завтрак', 'обед', 'ужин')) NOT NULL,
                ingredients TEXT NOT NULL,
                instructions TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        ''')

        # Таблица отзывов
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recipe_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                rating INTEGER CHECK(rating BETWEEN 1 AND 5),
                comment TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (recipe_id) REFERENCES recipes(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        ''')
        self.conn.commit()

    # === Методы для пользователей ===
    def add_user(self, user_id: int, username: str = None):
        """Добавить/обновить пользователя"""
        self.cursor.execute(
            """INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)""",
            (user_id, username)
        )
        # Обновляем username, если он изменился
        if username is not None:
            self.cursor.execute(
                "UPDATE users SET username = ? WHERE user_id = ?",
                (username, user_id)
            )
        self.conn.commit()

    def user_has_consent(self, user_id: int) -> bool:
        """Проверить согласие"""
        self.cursor.execute(
            "SELECT consent_given FROM users WHERE user_id = ?",
            (user_id,)
        )
        result = self.cursor.fetchone()
        return bool(result and result[0])

    def give_consent(self, user_id: int):
        """Записать согласие"""
        self.cursor.execute(
            "UPDATE users SET consent_given = 1, consent_date = CURRENT_TIMESTAMP WHERE user_id = ?",
            (user_id,)
        )
        self.conn.commit()

    # === Методы для рецептов ===
    def add_recipe(self, user_id: int, title: str, category: str, ingredients: str, instructions: str):
        self.cursor.execute(
            "INSERT INTO recipes (user_id, title, category, ingredients, instructions) VALUES (?, ?, ?, ?, ?)",
            (user_id, title, category, ingredients, instructions)
        )
        self.conn.commit()
        return self.cursor.lastrowid

    def get_user_recipes(self, user_id: int) -> List[Tuple]:
        self.cursor.execute(
            "SELECT id, title, category FROM recipes WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,)
        )
        return self.cursor.fetchall()

    def get_recipe(self, recipe_id: int) -> Optional[Tuple]:
        self.cursor.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,))
        return self.cursor.fetchone()

    def update_recipe(self, recipe_id: int, title: str, category: str, ingredients: str, instructions: str):
        self.cursor.execute(
            "UPDATE recipes SET title=?, category=?, ingredients=?, instructions=? WHERE id=?",
            (title, category, ingredients, instructions, recipe_id)
        )
        self.conn.commit()

    def delete_recipe(self, recipe_id: int):
        self.cursor.execute("DELETE FROM recipes WHERE id = ?", (recipe_id,))
        self.conn.commit()

    def search_recipes(self, query: str) -> List[Tuple]:
        self.cursor.execute(
            "SELECT id, title, category FROM recipes WHERE title LIKE ? OR ingredients LIKE ?",
            (f"%{query}%", f"%{query}%")
        )
        return self.cursor.fetchall()

    # === Методы для отзывов ===
    def add_review(self, recipe_id: int, user_id: int, rating: int, comment: str):
        self.cursor.execute(
            "INSERT INTO reviews (recipe_id, user_id, rating, comment) VALUES (?, ?, ?, ?)",
            (recipe_id, user_id, rating, comment)
        )
        self.conn.commit()

    def get_reviews(self, recipe_id: int) -> List[Tuple]:
        self.cursor.execute(
            "SELECT rating, comment, created_at FROM reviews WHERE recipe_id = ? ORDER BY created_at DESC",
            (recipe_id,)
        )
        return self.cursor.fetchall()

    # === Удаление данных пользователя при отзыве согласия ===
    def revoke_user_data(self, user_id: int):
        """Полное удаление всех данных пользователя при отзыве согласия"""
        # Удаляем в правильном порядке (из-за внешних ключей)
        self.cursor.execute("DELETE FROM reviews WHERE user_id = ?", (user_id,))
        self.cursor.execute("DELETE FROM recipes WHERE user_id = ?", (user_id,))
        self.cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        self.conn.commit()
        print(f"✅ Пользователь {user_id} полностью удалён из базы")

    def close(self):
        self.conn.close()