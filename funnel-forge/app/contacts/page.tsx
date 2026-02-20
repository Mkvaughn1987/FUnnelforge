"use client";

import { useState, useRef } from "react";
import PageHeader from "@/components/PageHeader";

/* ── Types ── */
interface Contact {
  id: string;
  firstName: string;
  lastName: string;
  email: string;
  personalEmail: string;
  company: string;
  title: string;
  phone: string;
  workPhone: string;
  mobilePhone: string;
  linkedIn: string;
  city: string;
  state: string;
  industry: string;
  tags: string[];
}

const EMPTY_CONTACT: Omit<Contact, "id"> = {
  firstName: "",
  lastName: "",
  email: "",
  personalEmail: "",
  company: "",
  title: "",
  phone: "",
  workPhone: "",
  mobilePhone: "",
  linkedIn: "",
  city: "",
  state: "",
  industry: "",
  tags: [],
};

const SAMPLE_CONTACTS: Contact[] = [
  { id: "1", firstName: "Sarah", lastName: "Chen", email: "sarah@acmecorp.com", personalEmail: "", company: "Acme Corp", title: "VP of Sales", phone: "(555) 123-4567", workPhone: "", mobilePhone: "", linkedIn: "", city: "Nashville", state: "Tennessee", industry: "Technology", tags: ["prospect"] },
  { id: "2", firstName: "Marcus", lastName: "Rivera", email: "marcus@globex.io", personalEmail: "", company: "Globex Inc", title: "CTO", phone: "(555) 234-5678", workPhone: "", mobilePhone: "", linkedIn: "", city: "Denver", state: "Colorado", industry: "Software", tags: ["lead", "tech"] },
  { id: "3", firstName: "Emily", lastName: "Okafor", email: "emily@brightwavehq.com", personalEmail: "", company: "Brightwave HQ", title: "Marketing Director", phone: "(555) 345-6789", workPhone: "", mobilePhone: "", linkedIn: "", city: "Atlanta", state: "Georgia", industry: "Marketing", tags: ["lead"] },
  { id: "4", firstName: "James", lastName: "Thornton", email: "james@nimbusdata.co", personalEmail: "", company: "Nimbus Data", title: "CEO", phone: "(555) 456-7890", workPhone: "", mobilePhone: "", linkedIn: "", city: "Austin", state: "Texas", industry: "Data", tags: ["prospect", "decision-maker"] },
  { id: "5", firstName: "Priya", lastName: "Mehta", email: "priya@zenithsoftware.com", personalEmail: "", company: "Zenith Software", title: "Head of Partnerships", phone: "(555) 567-8901", workPhone: "", mobilePhone: "", linkedIn: "", city: "San Francisco", state: "California", industry: "SaaS", tags: ["partner"] },
];

/* ── CSV / TSV parser that handles quoted fields ── */
function parseCSVRow(line: string, delimiter: string): string[] {
  const fields: string[] = [];
  let current = "";
  let inQuotes = false;

  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (inQuotes) {
      if (ch === '"' && line[i + 1] === '"') {
        current += '"';
        i++;
      } else if (ch === '"') {
        inQuotes = false;
      } else {
        current += ch;
      }
    } else {
      if (ch === '"') {
        inQuotes = true;
      } else if (ch === delimiter) {
        fields.push(current.trim());
        current = "";
      } else {
        current += ch;
      }
    }
  }
  fields.push(current.trim());
  return fields;
}

/* ── Column name mapping for ZoomInfo / generic spreadsheets ── */
function findColumn(row: Record<string, string>, ...keys: string[]): string {
  for (const key of keys) {
    if (row[key] !== undefined && row[key] !== "") return row[key];
  }
  return "";
}

export default function ContactsPage() {
  const [contacts, setContacts] = useState<Contact[]>(SAMPLE_CONTACTS);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [editingContact, setEditingContact] = useState<Contact | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [formData, setFormData] = useState<Omit<Contact, "id">>(EMPTY_CONTACT);
  const [tagInput, setTagInput] = useState("");
  const [importCount, setImportCount] = useState<number | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  /* ── Filtering ── */
  const filtered = contacts.filter((c) => {
    const q = search.toLowerCase();
    return (
      c.firstName.toLowerCase().includes(q) ||
      c.lastName.toLowerCase().includes(q) ||
      c.email.toLowerCase().includes(q) ||
      c.personalEmail.toLowerCase().includes(q) ||
      c.company.toLowerCase().includes(q) ||
      c.title.toLowerCase().includes(q) ||
      c.city.toLowerCase().includes(q) ||
      c.state.toLowerCase().includes(q) ||
      c.industry.toLowerCase().includes(q)
    );
  });

  /* ── Handlers ── */
  const toggleSelect = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selected.size === filtered.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(filtered.map((c) => c.id)));
    }
  };

  const deleteSelected = () => {
    setContacts((prev) => prev.filter((c) => !selected.has(c.id)));
    setSelected(new Set());
  };

  const openAdd = () => {
    setEditingContact(null);
    setFormData({ ...EMPTY_CONTACT });
    setTagInput("");
    setShowForm(true);
  };

  const openEdit = (contact: Contact) => {
    setEditingContact(contact);
    const { id: _, ...rest } = contact;
    setFormData({ ...rest, tags: [...contact.tags] });
    setTagInput("");
    setShowForm(true);
  };

  const saveContact = () => {
    if (!formData.firstName || !formData.email) return;
    if (editingContact) {
      setContacts((prev) =>
        prev.map((c) => (c.id === editingContact.id ? { ...formData, id: editingContact.id } : c))
      );
    } else {
      setContacts((prev) => [...prev, { ...formData, id: crypto.randomUUID() }]);
    }
    setShowForm(false);
  };

  const addTag = () => {
    const tag = tagInput.trim().toLowerCase();
    if (tag && !formData.tags.includes(tag)) {
      setFormData((f) => ({ ...f, tags: [...f.tags, tag] }));
    }
    setTagInput("");
  };

  const removeTag = (tag: string) => {
    setFormData((f) => ({ ...f, tags: f.tags.filter((t) => t !== tag) }));
  };

  const handleCSVImport = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      const text = ev.target?.result as string;
      const lines = text.split(/\r?\n/).filter((l) => l.trim());
      if (lines.length < 2) return;

      // Auto-detect delimiter: tab vs comma
      const firstLine = lines[0];
      const delimiter = firstLine.includes("\t") ? "\t" : ",";

      const headers = parseCSVRow(firstLine, delimiter).map((h) => h.toLowerCase().replace(/['"]/g, "").trim());
      const newContacts: Contact[] = [];

      for (let i = 1; i < lines.length; i++) {
        const values = parseCSVRow(lines[i], delimiter);
        if (values.length < 2) continue;

        const row: Record<string, string> = {};
        headers.forEach((h, idx) => (row[h] = values[idx] || ""));

        // Map columns — supports ZoomInfo, HubSpot, Salesforce, and generic CSVs
        const email = findColumn(row,
          "work email", "email", "email address", "e-mail", "workemail",
          "email1", "primary email", "business email"
        );
        const personalEmail = findColumn(row,
          "personal email", "personalemail", "personal e-mail",
          "email2", "secondary email", "other email"
        );
        const firstName = findColumn(row,
          "first name", "firstname", "first_name", "given name", "givenname"
        );
        const lastName = findColumn(row,
          "last name", "lastname", "last_name", "surname", "family name"
        );

        // Skip rows with no email and no name
        if (!email && !personalEmail && !firstName) continue;

        const company = findColumn(row,
          "company", "company name", "companyname", "organization", "account",
          "account name", "zoominfo company"
        );
        const title = findColumn(row,
          "job title", "title", "jobtitle", "job_title", "position",
          "role", "designation"
        );
        const phone = findColumn(row,
          "phone", "phone number", "direct phone", "direct phone number",
          "hq phone", "company phone", "business phone"
        );
        const workPhone = findColumn(row,
          "work phone", "workphone", "office phone", "company hq phone"
        );
        const mobilePhone = findColumn(row,
          "mobile phone", "mobilephone", "mobile", "cell", "cell phone",
          "mobile phone number"
        );
        const linkedIn = findColumn(row,
          "linkedin", "linkedin url", "linkedinurl", "linkedin profile",
          "person linkedin url", "linkedin contact profile url"
        );
        const city = findColumn(row,
          "city", "person city", "personcity", "contact city",
          "mailing city", "address city"
        );
        const state = findColumn(row,
          "state", "person state", "personstate", "contact state",
          "mailing state", "region", "province", "address state"
        );
        const industry = findColumn(row,
          "industry", "primary industry", "company industry",
          "primary sub-industry", "secondary industry"
        );

        newContacts.push({
          id: crypto.randomUUID(),
          firstName,
          lastName,
          email: email || personalEmail,
          personalEmail: email ? personalEmail : "",
          company,
          title,
          phone,
          workPhone,
          mobilePhone,
          linkedIn,
          city,
          state,
          industry,
          tags: [],
        });
      }

      if (newContacts.length > 0) {
        setContacts((prev) => [...prev, ...newContacts]);
        setImportCount(newContacts.length);
        setTimeout(() => setImportCount(null), 4000);
      }
    };
    reader.readAsText(file);
    e.target.value = "";
  };

  /* ── Form field config ── */
  const formFields: { key: keyof Omit<Contact, "id" | "tags">; label: string; placeholder: string; span2?: boolean }[] = [
    { key: "firstName", label: "First Name", placeholder: "John" },
    { key: "lastName", label: "Last Name", placeholder: "Doe" },
    { key: "email", label: "Work Email", placeholder: "john@company.com", span2: true },
    { key: "personalEmail", label: "Personal Email", placeholder: "john@gmail.com", span2: true },
    { key: "company", label: "Company", placeholder: "Acme Corp" },
    { key: "title", label: "Job Title", placeholder: "VP of Sales" },
    { key: "phone", label: "Phone", placeholder: "(555) 123-4567" },
    { key: "mobilePhone", label: "Mobile Phone", placeholder: "(555) 987-6543" },
    { key: "workPhone", label: "Work Phone", placeholder: "(555) 111-2222" },
    { key: "linkedIn", label: "LinkedIn URL", placeholder: "https://linkedin.com/in/..." },
    { key: "city", label: "City", placeholder: "Nashville" },
    { key: "state", label: "State", placeholder: "Tennessee" },
    { key: "industry", label: "Industry", placeholder: "Technology" },
  ];

  return (
    <div>
      <PageHeader title="Contacts" subtitle="Manage your contact lists and segments." />

      {/* ── Import success toast ── */}
      {importCount !== null && (
        <div className="mb-4 px-4 py-3 rounded-lg bg-green-400/10 border border-green-400/30 text-green-400 text-sm font-medium flex items-center gap-2">
          <svg className="w-4 h-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
          </svg>
          Successfully imported {importCount} contact{importCount !== 1 ? "s" : ""}
        </div>
      )}

      {/* ── Top bar ── */}
      <div className="flex flex-wrap items-center gap-3 mb-6">
        {/* Search */}
        <div className="relative flex-1 min-w-[240px]">
          <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-secondary" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
          </svg>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search contacts..."
            className="w-full pl-10 pr-4 py-2.5 rounded-lg bg-surface border border-border text-text-primary placeholder:text-text-secondary/50 focus:outline-none focus:border-accent-blue transition-colors text-sm"
          />
        </div>

        {/* Actions */}
        <button onClick={openAdd} className="px-4 py-2.5 rounded-lg bg-accent-blue text-white text-sm font-medium hover:bg-accent-blue/90 transition-colors flex items-center gap-2">
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
          </svg>
          Add Contact
        </button>
        <button onClick={() => fileRef.current?.click()} className="px-4 py-2.5 rounded-lg bg-bg border border-border text-text-secondary text-sm font-medium hover:text-text-primary hover:border-accent-blue/40 transition-colors flex items-center gap-2">
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5m-13.5-9L12 3m0 0 4.5 4.5M12 3v13.5" />
          </svg>
          Import CSV
        </button>
        <input ref={fileRef} type="file" accept=".csv,.tsv,.txt" onChange={handleCSVImport} className="hidden" />
        {selected.size > 0 && (
          <button onClick={deleteSelected} className="px-4 py-2.5 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm font-medium hover:bg-red-500/20 transition-colors">
            Delete ({selected.size})
          </button>
        )}
      </div>

      {/* ── Contact count ── */}
      <p className="text-text-secondary text-sm mb-3">
        {filtered.length} contact{filtered.length !== 1 ? "s" : ""}
        {search && ` matching "${search}"`}
      </p>

      {/* ── Table ── */}
      <div className="bg-surface rounded-xl border border-border overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-bg/50">
                <th className="px-4 py-3 text-left w-10">
                  <input
                    type="checkbox"
                    checked={filtered.length > 0 && selected.size === filtered.length}
                    onChange={toggleSelectAll}
                    className="rounded border-border accent-accent-blue"
                  />
                </th>
                <th className="px-4 py-3 text-left text-text-secondary font-medium">Name</th>
                <th className="px-4 py-3 text-left text-text-secondary font-medium">Email</th>
                <th className="px-4 py-3 text-left text-text-secondary font-medium hidden md:table-cell">Company</th>
                <th className="px-4 py-3 text-left text-text-secondary font-medium hidden lg:table-cell">Title</th>
                <th className="px-4 py-3 text-left text-text-secondary font-medium hidden xl:table-cell">Location</th>
                <th className="px-4 py-3 text-left text-text-secondary font-medium hidden xl:table-cell">Phone</th>
                <th className="px-4 py-3 text-left text-text-secondary font-medium hidden 2xl:table-cell">LinkedIn</th>
                <th className="px-4 py-3 w-16" />
              </tr>
            </thead>
            <tbody>
              {filtered.map((contact) => (
                <tr key={contact.id} className="border-b border-border last:border-0 hover:bg-surface-hover/50 transition-colors">
                  <td className="px-4 py-3">
                    <input
                      type="checkbox"
                      checked={selected.has(contact.id)}
                      onChange={() => toggleSelect(contact.id)}
                      className="rounded border-border accent-accent-blue"
                    />
                  </td>
                  <td className="px-4 py-3 text-text-primary font-medium whitespace-nowrap">
                    {contact.firstName} {contact.lastName}
                  </td>
                  <td className="px-4 py-3 text-text-secondary max-w-[200px] truncate">{contact.email}</td>
                  <td className="px-4 py-3 text-text-secondary hidden md:table-cell">{contact.company}</td>
                  <td className="px-4 py-3 text-text-secondary hidden lg:table-cell max-w-[180px] truncate">{contact.title}</td>
                  <td className="px-4 py-3 text-text-secondary hidden xl:table-cell whitespace-nowrap">
                    {[contact.city, contact.state].filter(Boolean).join(", ")}
                  </td>
                  <td className="px-4 py-3 text-text-secondary hidden xl:table-cell whitespace-nowrap">
                    {contact.mobilePhone || contact.phone || contact.workPhone || "—"}
                  </td>
                  <td className="px-4 py-3 hidden 2xl:table-cell">
                    {contact.linkedIn ? (
                      <a
                        href={contact.linkedIn}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-accent-blue hover:text-accent-blue/80 transition-colors flex items-center gap-1.5"
                      >
                        <svg className="w-4 h-4 flex-shrink-0" viewBox="0 0 24 24" fill="currentColor">
                          <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 0 1-2.063-2.065 2.064 2.064 0 1 1 2.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z" />
                        </svg>
                        Profile
                      </a>
                    ) : (
                      <span className="text-text-secondary/40">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() => openEdit(contact)}
                      className="text-text-secondary hover:text-accent-blue transition-colors"
                      title="Edit contact"
                    >
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L10.582 16.07a4.5 4.5 0 0 1-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 0 1 1.13-1.897l8.932-8.931Zm0 0L19.5 7.125" />
                      </svg>
                    </button>
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={9} className="px-4 py-12 text-center text-text-secondary">
                    {search ? "No contacts match your search." : "No contacts yet. Add one or import a CSV."}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* ── Add / Edit Modal ── */}
      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-surface rounded-xl border border-border p-6 w-full max-w-2xl mx-4 shadow-2xl max-h-[90vh] overflow-y-auto">
            <h2 className="text-xl font-semibold mb-5">
              {editingContact ? "Edit Contact" : "Add Contact"}
            </h2>

            <div className="grid grid-cols-2 gap-4 mb-4">
              {formFields.map((field) => (
                <div key={field.key} className={field.span2 ? "col-span-2" : ""}>
                  <label className="block text-xs font-medium text-text-secondary mb-1 uppercase tracking-wide">
                    {field.label}
                  </label>
                  <input
                    type={field.key.includes("email") ? "email" : field.key === "linkedIn" ? "url" : "text"}
                    value={formData[field.key]}
                    onChange={(e) => setFormData((f) => ({ ...f, [field.key]: e.target.value }))}
                    placeholder={field.placeholder}
                    className="w-full px-3 py-2 rounded-lg bg-bg border border-border text-text-primary placeholder:text-text-secondary/40 text-sm focus:outline-none focus:border-accent-blue transition-colors"
                  />
                </div>
              ))}
            </div>

            {/* Tags */}
            <div className="mb-5">
              <label className="block text-xs font-medium text-text-secondary mb-1 uppercase tracking-wide">Tags</label>
              <div className="flex flex-wrap gap-1.5 mb-2">
                {formData.tags.map((tag) => (
                  <span key={tag} className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-accent-blue/10 text-accent-blue text-xs">
                    {tag}
                    <button onClick={() => removeTag(tag)} className="hover:text-red-400 transition-colors">&times;</button>
                  </span>
                ))}
              </div>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={tagInput}
                  onChange={(e) => setTagInput(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addTag(); } }}
                  placeholder="Add tag..."
                  className="flex-1 px-3 py-2 rounded-lg bg-bg border border-border text-text-primary placeholder:text-text-secondary/40 text-sm focus:outline-none focus:border-accent-blue transition-colors"
                />
                <button onClick={addTag} className="px-3 py-2 rounded-lg bg-bg border border-border text-text-secondary text-sm hover:text-accent-blue hover:border-accent-blue/40 transition-colors">
                  Add
                </button>
              </div>
            </div>

            <div className="flex justify-end gap-3">
              <button onClick={() => setShowForm(false)} className="px-4 py-2 rounded-lg bg-bg border border-border text-text-secondary text-sm font-medium hover:text-text-primary transition-colors">
                Cancel
              </button>
              <button onClick={saveContact} className="px-5 py-2 rounded-lg bg-accent-blue text-white text-sm font-medium hover:bg-accent-blue/90 transition-colors">
                {editingContact ? "Save Changes" : "Add Contact"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
