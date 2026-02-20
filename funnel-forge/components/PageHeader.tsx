import Image from "next/image";

interface PageHeaderProps {
  title: string;
  subtitle: string;
}

export default function PageHeader({ title, subtitle }: PageHeaderProps) {
  return (
    <div
      className="relative mb-8 -mx-8 -mt-8 px-8 py-6 overflow-hidden border-b border-border"
      style={{
        background: "linear-gradient(135deg, color-mix(in srgb, var(--color-accent-blue) 6%, transparent) 0%, color-mix(in srgb, var(--color-accent-purple) 4%, transparent) 50%, transparent 100%)",
      }}
    >
      <div className="flex items-center gap-4">
        <Image
          src="/logo.png"
          alt="FlowDrop"
          width={134}
          height={90}
          className="h-9 w-auto"
          unoptimized
        />
        <div>
          <h1 className="text-3xl">{title}</h1>
          <p className="text-text-secondary text-sm mt-0.5">{subtitle}</p>
        </div>
      </div>
    </div>
  );
}
