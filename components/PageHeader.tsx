import Image from "next/image";
interface PageHeaderProps {
  title: string;
  subtitle: string;
}
export default function PageHeader({ title, subtitle }: PageHeaderProps) {
  return (
    <div className="relative mb-8 -mx-8 -mt-8 px-8 py-6 overflow-hidden border-b border-border"
      style={{
        background: "linear-gradient(135deg, rgba(56,197,178,0.06) 0%, rgba(91,175,214,0.04) 50%, transparent 100%)",
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
