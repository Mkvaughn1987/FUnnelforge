import { NextRequest, NextResponse } from "next/server";
import OpenAI from "openai";

const openai = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY,
});

const SYSTEM_PROMPT = `You are an expert email marketing strategist for FlowDrop, an email sequencer app for sales teams. Your job is to help users create effective email campaign sequences.

When a user describes their campaign goals, audience, and tone:
1. Ask clarifying questions if needed
2. Generate a complete email sequence (typically 3-5 emails)
3. For each email, provide: subject line, email body, and recommended send timing
4. Keep emails concise, professional, and conversion-focused
5. Adapt tone to the user's request (formal, friendly, urgent, etc.)

Format your email sequences clearly with headers for each email step.`;

export async function POST(req: NextRequest) {
  try {
    const { messages } = await req.json();

    if (!messages || !Array.isArray(messages)) {
      return NextResponse.json(
        { error: "Messages array is required" },
        { status: 400 }
      );
    }

    const completion = await openai.chat.completions.create({
      model: "gpt-4o-mini",
      messages: [
        { role: "system", content: SYSTEM_PROMPT },
        ...messages.map((m: { role: string; content: string }) => ({
          role: m.role as "user" | "assistant",
          content: m.content,
        })),
      ],
      temperature: 0.7,
      max_tokens: 2000,
    });

    const message = completion.choices[0]?.message?.content || "No response generated.";

    return NextResponse.json({ message });
  } catch (error: unknown) {
    console.error("OpenAI API error:", error);
    const errorMessage = error instanceof Error ? error.message : "Failed to generate response";
    return NextResponse.json(
      { error: errorMessage },
      { status: 500 }
    );
  }
}
