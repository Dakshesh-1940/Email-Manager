import email
from email.header import decode_header
import imaplib
import json
import os
import re
from openai import OpenAI
import psycopg2

# Load environment variables
DATABASE_URL = os.environ.get("DATABASE_URL")
IMAP_SERVER = os.environ.get("IMAP_SERVER", "imap.gmail.com")
EMAIL_USER = os.environ.get("EMAIL_USER")
EMAIL_PASS = os.environ.get("EMAIL_PASS")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)


def get_db_connection():
    return psycopg2.connect(DATABASE_URL)


def is_processed(conn, email_id):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM processed_emails WHERE email_id = %s", (email_id,)
        )
        return cur.fetchone() is not None


def mark_processed(conn, email_id):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO processed_emails (email_id) VALUES (%s) ON CONFLICT DO NOTHING",
            (email_id,),
        )
    conn.commit()


def save_todo(conn, email_id, title, category, importance, deadline, details):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO todos (email_id, title, category, importance, deadline, details)
            VALUES (%s, %s, %s, %s, %s, %s)
        """,
            (email_id, title, category, importance, deadline, details),
        )
    conn.commit()


def decode_str(header_value):
    if not header_value:
        return ""
    decoded_list = decode_header(header_value)
    text = ""
    for content, encoding in decoded_list:
        if isinstance(content, bytes):
            text += content.decode(encoding or "utf-8", errors="ignore")
        else:
            text += str(content)
    return text


def clean_body_text(text):
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_tasks_with_ai(subject, body):
    prompt = """
    You are an AI assistant analyzing college emails. Determine if this email contains actionable tasks or events (hackathon registration, exams, fee payment, assignment submission).
    Return ONLY a JSON object:
    {
      "has_actionable_task": true/false,
      "category": "Academic|Opportunity|Administrative|General",
      "importance": "High|Medium|Low",
      "task_title": "Clear action phrase",
      "deadline": "YYYY-MM-DD or 'Not specified'",
      "details": "Brief instructions"
    }
    """
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"Subject: {subject}\nBody: {body[:1500]}"},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as e:
        print(f"OpenAI error: {e}")
        return None


def run_check():
    print("Connecting to database...")
    conn = get_db_connection()
    try:
        print("Connecting to IMAP server...")
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select("INBOX")
        print("Successfully logged into IMAP!")

        status, messages = mail.search(None, "UNSEEN")
        email_ids = messages[0].split()
        print(f"Total UNSEEN emails found: {len(email_ids)}")

        for e_id in email_ids:
            str_id = e_id.decode("utf-8")
            print(f"Checking email ID: {str_id}")

            if is_processed(conn, str_id):
                print(f"Email ID {str_id} already processed. Skipping.")
                continue

            _, msg_data = mail.fetch(e_id, "(RFC822)")
            for part in msg_data:
                if isinstance(part, tuple):
                    msg = email.message_from_bytes(part[1])
                    subject = decode_str(msg["Subject"])
                    print(f"Processing Email Subject: '{subject}'")

                    body = ""
                    if msg.is_multipart():
                        for p in msg.walk():
                            if (
                                p.get_content_type() == "text/plain"
                                and "attachment"
                                not in str(p.get("Content-Disposition"))
                            ):
                                body = (
                                    p.get_payload(decode=True).decode(
                                        "utf-8", errors="ignore"
                                    )
                                    or ""
                                )
                                break
                    else:
                        body = (
                            msg.get_payload(decode=True).decode(
                                "utf-8", errors="ignore"
                            )
                            or ""
                        )

                    print("Sending email content to OpenAI for parsing...")
                    parsed = parse_tasks_with_ai(subject, clean_body_text(body))
                    print(f"AI Result: {parsed}")

                    if parsed and parsed.get("has_actionable_task"):
                        save_todo(
                            conn,
                            str_id,
                            parsed.get("task_title", subject),
                            parsed.get("category", "General"),
                            parsed.get("importance", "Medium"),
                            parsed.get("deadline", "Not specified"),
                            parsed.get("details", ""),
                        )
                        print(f"Successfully added task: {parsed.get('task_title')}")
                    else:
                        print("AI marked this email as non-actionable.")

                    mark_processed(conn, str_id)

        mail.logout()
        print("Finished processing emails.")
    except Exception as e:
        print(f"Error during execution: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    run_check()
