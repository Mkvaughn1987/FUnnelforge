"use client";

import type { Contact } from "@/lib/types";

interface Props {
  contacts: Contact[];
  selected: Set<string>;
  onToggleSelect: (id: string) => void;
  onToggleSelectAll: () => void;
  onEdit: (contact: Contact) => void;
  search: string;
}

export default function ContactTable({ contacts, selected, onToggleSelect, onToggleSelectAll, onEdit, search }: Props) {
  return (
    <div className="bg-surface rounded-xl border border-border overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-bg/50">
              <th className="px-4 py-3 text-left w-10">
                <input
                  type="checkbox"
                  checked={contacts.length > 0 && selected.size === contacts.length}
                  onChange={onToggleSelectAll}
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
            {contacts.map((contact) => (
              <tr key={contact.id} className="border-b border-border last:border-0 hover:bg-surface-hover/50 transition-colors">
                <td className="px-4 py-3">
                  <input
                    type="checkbox"
                    checked={selected.has(contact.id)}
                    onChange={() => onToggleSelect(contact.id)}
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
                  {contact.mobilePhone || contact.phone || contact.workPhone || "\u2014"}
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
                    <span className="text-text-secondary/40">{"\u2014"}</span>
                  )}
                </td>
                <td className="px-4 py-3">
                  <button
                    onClick={() => onEdit(contact)}
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
            {contacts.length === 0 && (
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
  );
}
