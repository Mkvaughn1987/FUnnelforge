"use client";

import { useState, useRef } from "react";
import PageHeader from "@/components/PageHeader";
import ContactTable from "@/components/contacts/ContactTable";
import ContactFormModal from "@/components/contacts/ContactFormModal";
import { Button, PlusIcon } from "@/components/ui";
import type { Contact } from "@/lib/types";
import { SAMPLE_CONTACTS, EMPTY_CONTACT } from "@/lib/sample-data";

/* ── CSV parser ── */
function parseCSVRow(line: string, delimiter: string): string[] {
  const fields: string[] = [];
  let current = "";
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (inQuotes) {
      if (ch === '"' && line[i + 1] === '"') { current += '"'; i++; }
      else if (ch === '"') { inQuotes = false; }
      else { current += ch; }
    } else {
      if (ch === '"') { inQuotes = true; }
      else if (ch === delimiter) { fields.push(current.trim()); current = ""; }
      else { current += ch; }
    }
  }
  fields.push(current.trim());
  return fields;
}

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
  const [importCount, setImportCount] = useState<number | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

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

  const toggleSelect = (id: string) => {
    setSelected((prev) => { const next = new Set(prev); if (next.has(id)) next.delete(id); else next.add(id); return next; });
  };

  const toggleSelectAll = () => {
    setSelected(selected.size === filtered.length ? new Set() : new Set(filtered.map((c) => c.id)));
  };

  const deleteSelected = () => {
    setContacts((prev) => prev.filter((c) => !selected.has(c.id)));
    setSelected(new Set());
  };

  const openAdd = () => {
    setEditingContact(null);
    setFormData({ ...EMPTY_CONTACT });
    setShowForm(true);
  };

  const openEdit = (contact: Contact) => {
    setEditingContact(contact);
    const { id: _, ...rest } = contact;
    setFormData({ ...rest, tags: [...contact.tags] });
    setShowForm(true);
  };

  const saveContact = () => {
    if (!formData.firstName || !formData.email) return;
    if (editingContact) {
      setContacts((prev) => prev.map((c) => (c.id === editingContact.id ? { ...formData, id: editingContact.id } : c)));
    } else {
      setContacts((prev) => [...prev, { ...formData, id: crypto.randomUUID() }]);
    }
    setShowForm(false);
  };

  const handleCSVImport = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      const text = ev.target?.result as string;
      const lines = text.split(/\r?\n/).filter((l) => l.trim());
      if (lines.length < 2) return;
      const delimiter = lines[0].includes("\t") ? "\t" : ",";
      const headers = parseCSVRow(lines[0], delimiter).map((h) => h.toLowerCase().replace(/['"]/g, "").trim());
      const newContacts: Contact[] = [];

      for (let i = 1; i < lines.length; i++) {
        const values = parseCSVRow(lines[i], delimiter);
        if (values.length < 2) continue;
        const row: Record<string, string> = {};
        headers.forEach((h, idx) => (row[h] = values[idx] || ""));

        const email = findColumn(row, "work email", "email", "email address", "e-mail", "workemail", "email1", "primary email", "business email");
        const personalEmail = findColumn(row, "personal email", "personalemail", "personal e-mail", "email2", "secondary email", "other email");
        const firstName = findColumn(row, "first name", "firstname", "first_name", "given name", "givenname");
        const lastName = findColumn(row, "last name", "lastname", "last_name", "surname", "family name");
        if (!email && !personalEmail && !firstName) continue;

        newContacts.push({
          id: crypto.randomUUID(),
          firstName, lastName,
          email: email || personalEmail,
          personalEmail: email ? personalEmail : "",
          company: findColumn(row, "company", "company name", "companyname", "organization", "account", "account name"),
          title: findColumn(row, "job title", "title", "jobtitle", "job_title", "position", "role"),
          phone: findColumn(row, "phone", "phone number", "direct phone", "direct phone number", "hq phone", "company phone"),
          workPhone: findColumn(row, "work phone", "workphone", "office phone"),
          mobilePhone: findColumn(row, "mobile phone", "mobilephone", "mobile", "cell", "cell phone"),
          linkedIn: findColumn(row, "linkedin", "linkedin url", "linkedinurl", "linkedin profile", "person linkedin url"),
          city: findColumn(row, "city", "person city", "personcity", "contact city"),
          state: findColumn(row, "state", "person state", "personstate", "contact state", "region"),
          industry: findColumn(row, "industry", "primary industry", "company industry"),
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

  return (
    <div>
      <PageHeader title="Contacts" subtitle="Manage your contact lists and segments." />

      {importCount !== null && (
        <div className="mb-4 px-4 py-3 rounded-lg bg-green-400/10 border border-green-400/30 text-green-400 text-sm font-medium flex items-center gap-2">
          <svg className="w-4 h-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
          </svg>
          Successfully imported {importCount} contact{importCount !== 1 ? "s" : ""}
        </div>
      )}

      {/* Top bar */}
      <div className="flex flex-wrap items-center gap-3 mb-6">
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
        <Button onClick={openAdd}><PlusIcon /> Add Contact</Button>
        <Button variant="secondary" onClick={() => fileRef.current?.click()}>
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5m-13.5-9L12 3m0 0 4.5 4.5M12 3v13.5" />
          </svg>
          Import CSV
        </Button>
        <input ref={fileRef} type="file" accept=".csv,.tsv,.txt" onChange={handleCSVImport} className="hidden" />
        {selected.size > 0 && (
          <Button variant="danger" onClick={deleteSelected}>Delete ({selected.size})</Button>
        )}
      </div>

      <p className="text-text-secondary text-sm mb-3">
        {filtered.length} contact{filtered.length !== 1 ? "s" : ""}
        {search && ` matching "${search}"`}
      </p>

      <ContactTable
        contacts={filtered}
        selected={selected}
        onToggleSelect={toggleSelect}
        onToggleSelectAll={toggleSelectAll}
        onEdit={openEdit}
        search={search}
      />

      <ContactFormModal
        open={showForm}
        onClose={() => setShowForm(false)}
        contact={editingContact}
        formData={formData}
        onFormChange={setFormData}
        onSave={saveContact}
      />
    </div>
  );
}
