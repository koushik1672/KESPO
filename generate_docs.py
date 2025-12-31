import os
from fpdf import FPDF
from datetime import datetime
from pathlib import Path

class SimplePDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 12)
        self.cell(0, 10, 'KESPO Project Code Documentation', 0, 1, 'C')
        self.cell(0, 10, f'Generated on {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', 0, 1, 'C')
        self.ln(10)

    def chapter_title(self, title):
        self.set_font('Arial', 'B', 12)
        self.set_fill_color(200, 220, 255)
        self.cell(0, 10, title, 0, 1, 'L', 1)
        self.ln(4)

def sanitize_text(text):
    """Replace or remove problematic Unicode characters"""
    if not text:
        return ""
    
    # Common Unicode replacements
    replacements = {
        '₹': 'Rs.',     # Indian Rupee symbol
        '–': '-',       # en dash
        '—': '--',      # em dash
        '“': '"',       # left double quote
        '”': '"',       # right double quote
        '‘': "'",       # left single quote
        '’': "'",       # right single quote
        '…': '...',     # ellipsis
        '―': '-',       # horizontal bar
        ' ': ' ',       # narrow no-break space
        '←': '<-',      # leftwards arrow
        '→': '->',      # rightwards arrow
        '↑': '(up)',    # upwards arrow
        '↓': '(down)',  # downwards arrow
    }
    
    # Apply replacements
    for k, v in replacements.items():
        text = text.replace(k, v)
    
    # Remove any remaining non-ASCII characters
    return ''.join(c if ord(c) < 128 and c not in '\x00-\x1f\x7f-\x9f' else ' ' 
                 for c in text)

def get_file_content(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as file:
            return sanitize_text(file.read())
    except Exception as e:
        try:
            with open(filepath, 'r', encoding='latin-1') as file:
                return sanitize_text(file.read())
        except Exception as e:
            print(f"Error reading {filepath}: {str(e)}")
            return f"[Error reading file: {str(e)}]"

def create_pdf_documentation(project_path, output_file):
    pdf = SimplePDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_font('Courier', '', 8)  # Use built-in Courier font
    
    added_sections = set()
    
    file_types = {
        'Python': ['.py'],
        'HTML': ['.html'],
        'CSS': ['.css'],
        'JavaScript': ['.js']
    }
    
    for root, _, files in os.walk(project_path):
        if any(x in root for x in ['venv', '__pycache__', '.git', '.idea', 'node_modules']):
            continue
            
        for file in sorted(files):
            file_path = Path(root) / file
            rel_path = file_path.relative_to(project_path)
            file_ext = file_path.suffix.lower()
            
            file_type = None
            for ftype, exts in file_types.items():
                if file_ext in exts:
                    file_type = ftype
                    break
            
            if file_type:
                try:
                    if file_type not in added_sections:
                        pdf.add_page()
                        pdf.chapter_title(f"{file_type} Files")
                        added_sections.add(file_type)
                    
                    content = get_file_content(file_path)
                    pdf.set_font('Arial', 'B', 10)
                    pdf.cell(0, 10, f"File: {rel_path}", 0, 1)
                    pdf.set_font('Courier', '', 8)
                    
                    lines = content.split('\n')
                    for i, line in enumerate(lines, 1):
                        try:
                            pdf.cell(0, 5, f"{i:4} | {line}", 0, 1)
                        except:
                            continue
                    
                    pdf.ln(5)
                except Exception as e:
                    print(f"Error processing {file_path}: {str(e)}")
                    continue
    
    try:
        pdf.output(output_file)
        print(f"Successfully created: {output_file}")
        return True
    except Exception as e:
        print(f"Error saving PDF: {str(e)}")
        alt_output = os.path.join(os.path.expanduser('~'), 'Desktop', 'kespo_documentation.pdf')
        try:
            pdf.output(alt_output)
            print(f"PDF saved to alternative location: {alt_output}")
            return True
        except Exception as e2:
            print(f"Failed to save PDF: {str(e2)}")
            return False

if __name__ == "__main__":
    project_path = os.path.dirname(os.path.abspath(__file__))
    output_file = os.path.join(project_path, "kespo_documentation.pdf")
    
    print(f"Generating documentation PDF to: {output_file}")
    if create_pdf_documentation(project_path, output_file):
        print("Documentation generated successfully!")
    else:
        print("Failed to generate documentation. Please check the error messages above.")