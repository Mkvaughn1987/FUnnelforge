"""
FunnelForge User Guide PDF Generator
"""

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, ListFlowable, ListItem, PageBreak, Table, TableStyle, Image
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.pdfgen import canvas
import os

# Colors matching FunnelForge branding
ACCENT_BLUE = HexColor("#4F7DF3")
DARK_BLUE = HexColor("#1E3A5F")
GREEN = HexColor("#10B981")
GRAY = HexColor("#6B7280")

# Logo paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOGO_LEFT = os.path.join(SCRIPT_DIR, "assets", "banner_left.png")
LOGO_RIGHT = os.path.join(SCRIPT_DIR, "assets", "banner_right.png")
LOGO_MAIN = os.path.join(SCRIPT_DIR, "assets", "funnelforge.png")

class NumberedCanvas(canvas.Canvas):
    """Custom canvas that adds logo header to each page."""

    def __init__(self, *args, **kwargs):
        canvas.Canvas.__init__(self, *args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        """Add headers to all pages."""
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_header()
            self.draw_page_footer(num_pages)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def draw_page_header(self):
        """Draw logo header on each page."""
        page_width, page_height = letter

        # Draw left logo (FunnelForge text logo)
        if os.path.exists(LOGO_LEFT):
            try:
                self.drawImage(LOGO_LEFT, 50, page_height - 50, width=100, height=35, preserveAspectRatio=True, mask='auto')
            except:
                pass

        # Draw right logo (FF icon)
        if os.path.exists(LOGO_RIGHT):
            try:
                self.drawImage(LOGO_RIGHT, page_width - 100, page_height - 50, width=45, height=35, preserveAspectRatio=True, mask='auto')
            except:
                pass

        # Draw a subtle line under the header
        self.setStrokeColor(HexColor("#E5E7EB"))
        self.setLineWidth(0.5)
        self.line(50, page_height - 60, page_width - 50, page_height - 60)

    def draw_page_footer(self, num_pages):
        """Draw page number footer."""
        page_width, page_height = letter
        page_num = self._pageNumber

        self.setFont("Helvetica", 9)
        self.setFillColor(GRAY)
        self.drawCentredString(page_width / 2, 30, f"Page {page_num} of {num_pages}")

def create_user_guide():
    doc = SimpleDocTemplate(
        "FunnelForge_UserGuide.pdf",
        pagesize=letter,
        rightMargin=72,
        leftMargin=72,
        topMargin=90,  # Extra space for header
        bottomMargin=72
    )

    # Styles
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=28,
        textColor=ACCENT_BLUE,
        spaceAfter=30,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )

    subtitle_style = ParagraphStyle(
        'Subtitle',
        parent=styles['Normal'],
        fontSize=14,
        textColor=GRAY,
        spaceAfter=40,
        alignment=TA_CENTER
    )

    heading1_style = ParagraphStyle(
        'Heading1Custom',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=DARK_BLUE,
        spaceBefore=20,
        spaceAfter=12,
        fontName='Helvetica-Bold'
    )

    heading2_style = ParagraphStyle(
        'Heading2Custom',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=ACCENT_BLUE,
        spaceBefore=15,
        spaceAfter=8,
        fontName='Helvetica-Bold'
    )

    body_style = ParagraphStyle(
        'BodyCustom',
        parent=styles['Normal'],
        fontSize=11,
        textColor=HexColor("#374151"),
        spaceAfter=8,
        leading=16
    )

    bullet_style = ParagraphStyle(
        'BulletCustom',
        parent=styles['Normal'],
        fontSize=11,
        textColor=HexColor("#374151"),
        leftIndent=20,
        spaceAfter=4,
        leading=14
    )

    tip_style = ParagraphStyle(
        'TipStyle',
        parent=styles['Normal'],
        fontSize=10,
        textColor=GREEN,
        leftIndent=15,
        spaceBefore=8,
        spaceAfter=8,
        borderColor=GREEN,
        borderWidth=1,
        borderPadding=5
    )

    # Build document content
    story = []

    # Title Page
    story.append(Spacer(1, 2*inch))
    story.append(Paragraph("FUNNEL FORGE", title_style))
    story.append(Paragraph("Email Sequencer", subtitle_style))
    story.append(Spacer(1, 0.5*inch))
    story.append(Paragraph("User Guide", ParagraphStyle('SubTitle2', parent=subtitle_style, fontSize=18, textColor=DARK_BLUE)))
    story.append(Spacer(1, 1*inch))
    story.append(Paragraph("Version 2.2", ParagraphStyle('Version', parent=body_style, alignment=TA_CENTER, textColor=GRAY)))
    story.append(PageBreak())

    # Table of Contents
    story.append(Paragraph("Table of Contents", heading1_style))
    story.append(Spacer(1, 0.2*inch))

    toc_items = [
        "1. Getting Started",
        "2. Dashboard Overview",
        "3. Creating a Campaign",
        "    3.1 Email Editor",
        "    3.2 Sequence and Attachments",
        "    3.3 Choose Contacts",
        "    3.4 Preview and Launch",
        "    3.5 Cancel Sequences",
        "4. Stay Connected",
        "5. Campaign Analytics",
        "6. Managing Contacts",
        "7. Tips and Best Practices"
    ]

    for item in toc_items:
        story.append(Paragraph(item, body_style))

    story.append(PageBreak())

    # Section 1: Getting Started
    story.append(Paragraph("1. Getting Started", heading1_style))
    story.append(Paragraph(
        "FunnelForge is your powerful email sequencing tool that integrates directly with Microsoft Outlook. "
        "Because emails are sent straight from your own inbox, campaigns maintain an average 90% deliverability "
        "rate, keeping your outreach personal, trusted, and out of spam folders.",
        body_style
    ))
    story.append(Spacer(1, 0.1*inch))

    story.append(Paragraph("Requirements:", heading2_style))
    story.append(Paragraph("&bull; Microsoft Outlook installed and configured", bullet_style))
    story.append(Paragraph("&bull; Windows operating system", bullet_style))
    story.append(Paragraph("&bull; Contact list in CSV format", bullet_style))
    story.append(Spacer(1, 0.1*inch))

    story.append(Paragraph("First Launch:", heading2_style))
    story.append(Paragraph(
        "When you first open FunnelForge, a welcome walkthrough introduces the key features. "
        "The app includes a default contact list and a default email template to help you get started right away. "
        "Look for the info icon on each page for quick tips.",
        body_style
    ))

    # Section 2: Dashboard
    story.append(PageBreak())
    story.append(Paragraph("2. Dashboard Overview", heading1_style))
    story.append(Paragraph(
        "The Dashboard is your home base for tracking everything across your campaigns.",
        body_style
    ))
    story.append(Spacer(1, 0.1*inch))

    story.append(Paragraph("Stats Cards:", heading2_style))
    story.append(Paragraph("&bull; <b>Emails Past 30 Days</b> - Total emails sent in the last month", bullet_style))
    story.append(Paragraph("&bull; <b>Responses</b> - Number of replies received across all campaigns", bullet_style))
    story.append(Paragraph("&bull; <b>Response Rate</b> - Percentage of contacts who replied", bullet_style))
    story.append(Paragraph("&bull; <b>Active Campaigns</b> - Number of currently running campaigns", bullet_style))
    story.append(Spacer(1, 0.1*inch))

    story.append(Paragraph("Active and Completed Tabs:", heading2_style))
    story.append(Paragraph(
        "Campaigns are organized into two tabs: <b>Active</b> (currently sending) and <b>Completed</b> (finished). "
        "Click on any campaign row to expand it and see details.",
        body_style
    ))
    story.append(Spacer(1, 0.1*inch))

    story.append(Paragraph("Expanded Campaign Details:", heading2_style))
    story.append(Paragraph("&bull; <b>Response Tracking</b> (left side) - Shows response count, emails removed, and a list of responders", bullet_style))
    story.append(Paragraph("&bull; <b>Email Schedule</b> (right side) - Shows the full send timeline", bullet_style))
    story.append(Paragraph("&bull; Click the <b>email count</b> to see the full list of emails", bullet_style))
    story.append(Paragraph("&bull; Click the <b>contact count</b> to see all contacts in the campaign", bullet_style))
    story.append(Spacer(1, 0.1*inch))

    story.append(Paragraph("Automatic Response Scanning:", heading2_style))
    story.append(Paragraph(
        "FunnelForge automatically scans your Outlook inbox for replies. When a response is detected, "
        "remaining follow-up emails for that contact are cancelled. Out-of-office replies are recognized "
        "and do not cancel the sequence.",
        body_style
    ))

    # Section 3: Creating a Campaign
    story.append(PageBreak())
    story.append(Paragraph("3. Creating a Campaign", heading1_style))
    story.append(Paragraph(
        "Creating a campaign follows four tabs across the top: Email Editor, Sequence &amp; Attachments, "
        "Choose Contacts, and Preview &amp; Launch. Use preset sequences or customize your own cadence.",
        body_style
    ))

    # 3.1 Email Editor
    story.append(Paragraph("3.1 Email Editor", heading2_style))
    story.append(Paragraph(
        "This is where you create your email sequence. Each email appears as a tab.",
        body_style
    ))
    story.append(Spacer(1, 0.1*inch))

    story.append(Paragraph("<b>Templates:</b>", body_style))
    story.append(Paragraph(
        "Use the <b>Your Templates</b> dropdown at the top of the page to load saved email sequences. "
        "Templates are organized into two categories:",
        body_style
    ))
    story.append(Paragraph("&bull; <b>Team Templates</b> \u2014 Shared by your team via OneDrive. Read-only.", bullet_style))
    story.append(Paragraph("&bull; <b>My Templates</b> \u2014 Your personal saved sequences.", bullet_style))
    story.append(Paragraph("&bull; Use <b>Save Template</b> to save your current sequence.", bullet_style))
    story.append(Paragraph("&bull; Choose <b>Save and Share</b> to publish a template to the Team folder for everyone.", bullet_style))
    story.append(Paragraph("&bull; Use <b>Explore Templates</b> to browse all available templates.", bullet_style))
    story.append(Spacer(1, 0.1*inch))

    story.append(Paragraph("<b>Creating Emails:</b>", body_style))
    story.append(Paragraph("&bull; Click <b>+ Add Email</b> to add a new email to the sequence", bullet_style))
    story.append(Paragraph("&bull; Give each email a name (shown on the tab)", bullet_style))
    story.append(Paragraph("&bull; Enter the subject line", bullet_style))
    story.append(Paragraph("&bull; Write your email body", bullet_style))
    story.append(Paragraph("&bull; Click <b>Delete Email</b> to remove the active email", bullet_style))
    story.append(Spacer(1, 0.1*inch))

    story.append(Paragraph("<b>Using Variables:</b>", body_style))
    story.append(Paragraph(
        "Personalize your emails using variables that are replaced with each contact's data:",
        body_style
    ))
    story.append(Paragraph("&bull; {FirstName} - Contact's first name", bullet_style))
    story.append(Paragraph("&bull; {LastName} - Contact's last name", bullet_style))
    story.append(Paragraph("&bull; {Company} - Contact's company", bullet_style))
    story.append(Paragraph("&bull; {JobTitle} - Contact's job title", bullet_style))
    story.append(Paragraph("&bull; {SenderName} - Your name (from signature)", bullet_style))
    story.append(Spacer(1, 0.1*inch))

    story.append(Paragraph("<b>Pasting from Word:</b>", body_style))
    story.append(Paragraph(
        "FunnelForge automatically cleans up text pasted from Microsoft Word. Smart quotes, "
        "bullets, em dashes, and other special characters are converted to plain-text equivalents "
        "so your emails display correctly for all recipients.",
        body_style
    ))
    story.append(Spacer(1, 0.1*inch))

    story.append(Paragraph("<b>Signature:</b> Click 'Add/Edit Signature' to set up your email signature. "
        "It is automatically appended to all outgoing emails.", body_style))

    # 3.2 Sequence and Attachments
    story.append(PageBreak())
    story.append(Paragraph("3.2 Sequence and Attachments", heading2_style))
    story.append(Paragraph(
        "Set the timing for each email, use preset sequences, and add attachments.",
        body_style
    ))
    story.append(Spacer(1, 0.1*inch))

    story.append(Paragraph("<b>Scheduling:</b>", body_style))
    story.append(Paragraph("&bull; Set Email 1's send date and time manually", bullet_style))
    story.append(Paragraph("&bull; For emails 2+, set the <b>Bus. days after</b> value (business days, weekends are skipped)", bullet_style))
    story.append(Paragraph("&bull; Click <b>Update Dates</b> to auto-compute all send dates from Email 1", bullet_style))
    story.append(Spacer(1, 0.1*inch))

    story.append(Paragraph("<b>Preset Sequences:</b>", body_style))
    story.append(Paragraph("&bull; Choose a proven cadence (3\u201310 emails) from the dropdown and click <b>Apply</b>", bullet_style))
    story.append(Paragraph("&bull; Click <b>Customize</b> to adjust the business days and send times before applying", bullet_style))
    story.append(Paragraph("&bull; Preset sequences set both the day spacing and recommended send times", bullet_style))
    story.append(Spacer(1, 0.1*inch))

    story.append(Paragraph("<b>Attachments:</b>", body_style))
    story.append(Paragraph("&bull; Click <b>Add / Delete</b> next to any email to manage attachments", bullet_style))
    story.append(Paragraph("&bull; Drag &amp; drop files directly into the attachment window", bullet_style))
    story.append(Paragraph("&bull; Supported formats: PDF, Word, Excel, Images, and more", bullet_style))
    story.append(Paragraph("&bull; Attachments are sent with that specific email only", bullet_style))

    # 3.3 Choose Contacts
    story.append(Paragraph("3.3 Choose Contacts", heading2_style))
    story.append(Paragraph(
        "Select or import the contact list for your campaign. The dropdown defaults to "
        "'Choose a list' each time you open FunnelForge \u2014 you must actively select a list before launching.",
        body_style
    ))
    story.append(Spacer(1, 0.1*inch))

    story.append(Paragraph("<b>Importing a New List:</b>", body_style))
    story.append(Paragraph("&bull; Click 'Import New List' to import a CSV file", bullet_style))
    story.append(Paragraph("&bull; FunnelForge auto-detects columns including: Email, First Name, Last Name, Company, Job Title, Mobile Phone, and Work Phone", bullet_style))
    story.append(Paragraph("&bull; The list is saved and available for future campaigns", bullet_style))
    story.append(Spacer(1, 0.1*inch))

    story.append(Paragraph("<b>Adding Individual Contacts:</b>", body_style))
    story.append(Paragraph("&bull; Click 'Add Contact' to add a single contact manually", bullet_style))
    story.append(Paragraph("&bull; Fill in the contact details (Email is required)", bullet_style))
    story.append(Spacer(1, 0.1*inch))

    story.append(Paragraph("<b>Contact Table:</b>", body_style))
    story.append(Paragraph("&bull; Displays Email, First Name, Last Name, Company, Job Title, Mobile Phone, and Work Phone", bullet_style))
    story.append(Paragraph("&bull; Alternating row colors for easy reading", bullet_style))
    story.append(Paragraph("&bull; Select a contact and click 'Delete Contact' to remove them", bullet_style))

    # 3.4 Preview and Launch
    story.append(Paragraph("3.4 Preview and Launch", heading2_style))
    story.append(Paragraph(
        "Review your campaign and launch it. This page has three sections from top to bottom:",
        body_style
    ))
    story.append(Spacer(1, 0.1*inch))

    story.append(Paragraph("<b>Stay Connected:</b>", body_style))
    story.append(Paragraph("&bull; Choose a Stay Connected list for contacts who complete the sequence", bullet_style))
    story.append(Paragraph("&bull; When the last email in a sequence is sent, the contact is automatically added to this list for ongoing follow-up", bullet_style))
    story.append(Spacer(1, 0.1*inch))

    story.append(Paragraph("<b>Preview Emails:</b>", body_style))
    story.append(Paragraph("&bull; Click 'Send all emails to my inbox' to send a test preview of every email to yourself", bullet_style))
    story.append(Paragraph("&bull; The first time you use this, you'll be asked for your email address (saved for future use)", bullet_style))
    story.append(Spacer(1, 0.1*inch))

    story.append(Paragraph("<b>Run Funnel Forge:</b>", body_style))
    story.append(Paragraph("&bull; Click the <b>RUN FUNNEL FORGE</b> button to launch your campaign", bullet_style))
    story.append(Paragraph("&bull; You'll be asked to name your campaign", bullet_style))
    story.append(Paragraph("&bull; A snapshot shows: email count, contact count, date range, and total emails", bullet_style))
    story.append(Paragraph("&bull; Click <b>Run</b> to confirm and start sending", bullet_style))
    story.append(Paragraph("&bull; Outlook must be open for emails to send on schedule", bullet_style))

    # 3.5 Cancel Sequences
    story.append(Paragraph("3.5 Cancel Sequences", heading2_style))
    story.append(Paragraph(
        "Cancel pending emails for specific contacts or entire campaigns.",
        body_style
    ))
    story.append(Paragraph("&bull; Search by contact email or campaign name", bullet_style))
    story.append(Paragraph("&bull; Cancel individual emails or all pending emails matching your search", bullet_style))
    story.append(Paragraph("&bull; Cancelled emails are tracked as 'emails removed' on the Dashboard", bullet_style))

    # Section 4: Stay Connected
    story.append(PageBreak())
    story.append(Paragraph("4. Stay Connected", heading1_style))
    story.append(Paragraph(
        "After a campaign finishes, keep the conversation going with your contacts.",
        body_style
    ))
    story.append(Spacer(1, 0.1*inch))

    story.append(Paragraph("<b>How It Works:</b>", body_style))
    story.append(Paragraph("&bull; When a campaign sequence completes, contacts are automatically added to a Stay Connected list", bullet_style))
    story.append(Paragraph("&bull; You can also create new lists and add contacts manually at any time", bullet_style))
    story.append(Spacer(1, 0.1*inch))

    story.append(Paragraph("<b>Sending an Email:</b>", body_style))
    story.append(Paragraph("&bull; Select a list from the dropdown", bullet_style))
    story.append(Paragraph("&bull; Set the <b>Send Date</b> and <b>Time</b> at the top", bullet_style))
    story.append(Paragraph("&bull; Enter the email name, subject, and body", bullet_style))
    story.append(Paragraph("&bull; Use variables like {FirstName} to personalize", bullet_style))
    story.append(Paragraph("&bull; Add attachments if needed", bullet_style))
    story.append(Paragraph("&bull; Click <b>Send Email</b> to send to all contacts in the list", bullet_style))
    story.append(Spacer(1, 0.1*inch))

    story.append(Paragraph("<b>Activity Tab:</b>", body_style))
    story.append(Paragraph(
        "Track all sent messages in the Activity tab for each list.",
        body_style
    ))

    # Section 5: Campaign Analytics
    story.append(PageBreak())
    story.append(Paragraph("5. Campaign Analytics", heading1_style))
    story.append(Paragraph(
        "Track the performance of your campaigns directly from the Dashboard.",
        body_style
    ))
    story.append(Spacer(1, 0.1*inch))

    story.append(Paragraph("<b>Available Metrics:</b>", body_style))
    story.append(Paragraph("&bull; Emails sent per campaign", bullet_style))
    story.append(Paragraph("&bull; Response count and response rate", bullet_style))
    story.append(Paragraph("&bull; Emails removed (cancelled follow-ups from responses or manual cancellations)", bullet_style))
    story.append(Paragraph("&bull; Recent responders with dates", bullet_style))
    story.append(Spacer(1, 0.1*inch))

    story.append(Paragraph("<b>Response Tracking:</b>", body_style))
    story.append(Paragraph(
        "FunnelForge automatically scans your Outlook inbox for replies to campaign emails. "
        "When a response is detected:",
        body_style
    ))
    story.append(Paragraph("&bull; The response is logged with the sender and date", bullet_style))
    story.append(Paragraph("&bull; Remaining follow-up emails for that contact are automatically cancelled", bullet_style))
    story.append(Paragraph("&bull; Out-of-office replies are recognized and do <b>not</b> cancel the sequence", bullet_style))

    # Section 6: Managing Contacts
    story.append(Paragraph("6. Managing Contacts", heading1_style))
    story.append(Paragraph(
        "Use the Manage Contacts page to view, edit, or remove contacts from any saved list.",
        body_style
    ))
    story.append(Spacer(1, 0.1*inch))

    story.append(Paragraph("<b>CSV File Format:</b>", body_style))
    story.append(Paragraph(
        "Your contact lists should be CSV files. FunnelForge auto-detects columns:",
        body_style
    ))
    story.append(Spacer(1, 0.1*inch))

    # Create a simple table for CSV format
    table_data = [
        ['Column', 'Description', 'Required'],
        ['Email', 'Contact email address', 'Yes'],
        ['FirstName', 'First name', 'No'],
        ['LastName', 'Last name', 'No'],
        ['Company', 'Company name', 'No'],
        ['JobTitle', 'Job title / position', 'No'],
        ['MobilePhone', 'Mobile / cell phone', 'No'],
        ['WorkPhone', 'Work / office phone', 'No'],
    ]

    table = Table(table_data, colWidths=[1.5*inch, 2.5*inch, 1*inch])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), ACCENT_BLUE),
        ('TEXTCOLOR', (0, 0), (-1, 0), HexColor("#FFFFFF")),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('GRID', (0, 0), (-1, -1), 0.5, GRAY),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('PADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(table)
    story.append(Spacer(1, 0.2*inch))

    story.append(Paragraph("<b>Alternative Column Names:</b>", body_style))
    story.append(Paragraph(
        "FunnelForge recognizes many column name variations: 'Work Email' for Email, "
        "'First Name' (with space), 'Cell Phone' for MobilePhone, 'Direct Phone' for WorkPhone, etc.",
        body_style
    ))

    # Section 7: Tips and Best Practices
    story.append(PageBreak())
    story.append(Paragraph("7. Tips and Best Practices", heading1_style))

    story.append(Paragraph("<b>Email Timing:</b>", body_style))
    story.append(Paragraph("&bull; Send emails during business hours (9 AM - 5 PM)", bullet_style))
    story.append(Paragraph("&bull; Avoid Mondays and Fridays for best open rates", bullet_style))
    story.append(Paragraph("&bull; Space emails 2-3 business days apart", bullet_style))
    story.append(Spacer(1, 0.1*inch))

    story.append(Paragraph("<b>Email Content:</b>", body_style))
    story.append(Paragraph("&bull; Keep subject lines short and compelling", bullet_style))
    story.append(Paragraph("&bull; Personalize with {FirstName} and {Company}", bullet_style))
    story.append(Paragraph("&bull; Keep emails concise and focused", bullet_style))
    story.append(Paragraph("&bull; Include a clear call-to-action", bullet_style))
    story.append(Spacer(1, 0.1*inch))

    story.append(Paragraph("<b>Campaign Management:</b>", body_style))
    story.append(Paragraph("&bull; Save your templates frequently", bullet_style))
    story.append(Paragraph("&bull; Send a test preview to your inbox before launching", bullet_style))
    story.append(Paragraph("&bull; Monitor your Dashboard for responses", bullet_style))
    story.append(Paragraph("&bull; Keep Outlook open for emails to send on schedule", bullet_style))
    story.append(Spacer(1, 0.1*inch))

    story.append(Paragraph("<b>Deliverability:</b>", body_style))
    story.append(Paragraph("&bull; Emails send from your own Outlook inbox for maximum deliverability", bullet_style))
    story.append(Paragraph("&bull; Campaigns maintain an average 90% deliverability rate", bullet_style))
    story.append(Paragraph("&bull; Your outreach stays personal, trusted, and out of spam folders", bullet_style))
    story.append(Spacer(1, 0.1*inch))

    story.append(Paragraph("<b>Troubleshooting:</b>", body_style))
    story.append(Paragraph("&bull; If emails aren't sending, make sure Outlook is open", bullet_style))
    story.append(Paragraph("&bull; If contacts aren't importing, verify CSV has an Email column", bullet_style))
    story.append(Paragraph("&bull; If variables aren't replacing, check column names match", bullet_style))
    story.append(Paragraph("&bull; Look for the info icon on each page for page-specific help", bullet_style))
    story.append(Spacer(1, 0.3*inch))

    # Footer
    story.append(Paragraph("\u2500" * 50, ParagraphStyle('Line', alignment=TA_CENTER, textColor=GRAY)))
    story.append(Spacer(1, 0.2*inch))
    story.append(Paragraph(
        "FunnelForge v2.2",
        ParagraphStyle('Footer2', parent=body_style, alignment=TA_CENTER, fontSize=9, textColor=GRAY)
    ))

    # Build PDF with custom canvas for headers
    doc.build(story, canvasmaker=NumberedCanvas)
    print("User guide created: FunnelForge_UserGuide.pdf")

if __name__ == "__main__":
    create_user_guide()
