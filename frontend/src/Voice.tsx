import { useEffect, useRef, useState } from "react";
import type { LocalAudioTrack, Room } from "livekit-client";
import { type Api, useAction } from "./api";
import { ErrorNotice } from "./components";

type Join = { session_id: string; url: string; token: string; expires_at: string };
type Snapshot = { status: string; events: { id: string; kind: string; run_id: string | null; metadata: { code?: string } }[] };

export default function Voice({ api, conversationId, changed, busyChanged, disabled = false }: {
  api: Api; conversationId: string; changed: () => void; busyChanged: (value: boolean) => void; disabled?: boolean;
}) {
  const [session, setSession] = useState<Join>();
  const [status, setStatus] = useState("offline");
  const [notice, setNotice] = useState("");
  const [events, setEvents] = useState<Snapshot["events"]>([]);
  const [audioBlocked, setAudioBlocked] = useState(false);
  const mounted = useRef(true);
  const connection = useRef<{ room?: Room; microphone?: LocalAudioTrack; sessionId?: string }>({});
  const turn = useRef("");
  const action = useAction();
  const callbacks = useRef({ changed, busyChanged });
  callbacks.current = { changed, busyChanged };
  useEffect(() => {
    if (status !== "listening") void connection.current.microphone?.mute();
  }, [status]);

  async function release() {
    const current = connection.current;
    connection.current = {};
    current.microphone?.stop();
    await current.room?.disconnect();
    if (current.sessionId) await api(`/voice/sessions/${current.sessionId}/close`, {}).catch(() => {});
    callbacks.current.busyChanged(false);
  }
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; void release(); };
  }, []);

  useEffect(() => {
    if (!session) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    let previousEvents = 0;
    async function poll() {
      try {
        const data = await api<Snapshot>(`/voice/sessions/${session!.session_id}`);
        if (!active) return;
        setStatus(data.status);
        setEvents(data.events);
        if (data.events.length !== previousEvents) {
          previousEvents = data.events.length;
          if (data.events.some((e) => e.kind === "banking_answer")) callbacks.current.changed();
          const error = [...data.events].reverse().find((e) => e.kind === "speech_error");
          if (error) setNotice(`${error.metadata.code || "VOICE_UNAVAILABLE"}: Voice could not complete this step. Read saved history or try typing.`);
        }
        if (data.status === "closed") {
          await release();
          setSession(undefined);
          setStatus("offline");
          return;
        }
      } catch {
        if (!active) return;
        setNotice("Voice connection lost. Check saved history before retrying.");
        await release(); setSession(undefined); setStatus("offline");
        return;
      }
      if (active) timer = setTimeout(poll, 1000);
    }
    void poll();
    return () => { active = false; clearTimeout(timer); };
  }, [session, api]);

  async function connect() {
    setNotice("");
    await action.run(async () => {
      try {
        const { Room, RoomEvent, createLocalAudioTrack } = await import("livekit-client");
        const join = await api<Join>("/voice/sessions", { conversation_id: conversationId });
        connection.current.sessionId = join.session_id;
        if (!mounted.current) { await release(); return; }
        const room = new Room();
        connection.current.room = room;
        room.on(RoomEvent.TrackSubscribed, (track, _publication, participant) => {
          if (track.kind === "audio" && participant.identity === `worker-${join.session_id}`) {
            const audio = track.attach(); audio.autoplay = true;
            document.getElementById(`voice-audio-${conversationId}`)?.appendChild(audio);
          }
        });
        room.on(RoomEvent.TrackUnsubscribed, (track) => track.detach().forEach((element) => element.remove()));
        room.on(RoomEvent.Disconnected, () => {
          if (connection.current.room !== room) return;
          setNotice("Voice disconnected. Start a new session to reconnect."); void release(); setSession(undefined); setStatus("offline");
        });
        room.on(RoomEvent.AudioPlaybackStatusChanged, () => setAudioBlocked(!room.canPlaybackAudio));
        await room.connect(join.url, join.token);
        if (!mounted.current) { await release(); return; }
        void room.startAudio().catch(() => { if (mounted.current) setAudioBlocked(true); });
        const microphone = await createLocalAudioTrack({ echoCancellation: true, noiseSuppression: true });
        connection.current.microphone = microphone;
        if (!mounted.current) { await release(); return; }
        await microphone.mute();
        await room.localParticipant.publishTrack(microphone);
        setSession(join); setStatus("ready"); setEvents([]);
        callbacks.current.busyChanged(true);
      } catch (error) { await release(); throw error; }
    });
  }
  async function command(kind: "listen" | "send" | "interrupt" | "close") {
    if (!session) return;
    await action.run(async () => {
      setNotice("");
      if (kind === "listen") turn.current = crypto.randomUUID();
      if (kind !== "listen") await connection.current.microphone?.mute();
      if (kind === "interrupt" || kind === "listen") document.querySelectorAll<HTMLAudioElement>(`#voice-audio-${conversationId} audio`).forEach((audio) => { audio.muted = kind === "interrupt"; });
      if (kind === "send") await new Promise((resolve) => setTimeout(resolve, 300));
      const result = await api<{ status: string }>(`/voice/sessions/${session.session_id}/${kind}`, { turn_id: turn.current || null });
      if (kind === "listen") await connection.current.microphone?.unmute();
      if (kind === "close") { await release(); setSession(undefined); setStatus("offline"); callbacks.current.changed(); }
      else setStatus(result.status);
    });
  }
  return <section className="notice" aria-label="Browser voice">
    <h3>Browser voice</h3>
    <p>Speak with your demo banking assistant. Audio is sent to the configured speech provider; recordings are not stored. Transcripts and answers are saved in this conversation. Confirm banking actions using the review dialog, never by saying “yes”.</p>
    <p role="status">{status === "offline" ? "Voice is off." : `Voice: ${status}. Sessions last up to 5 minutes and 8 questions; each recording is limited to 30 seconds.`}</p>
    <div className="form-actions">
      {session && audioBlocked && <button type="button" className="secondary" onClick={() => void connection.current.room?.startAudio().then(() => setAudioBlocked(false)).catch(() => setNotice("Allow audio playback in your browser, then try again."))}>Enable speaker</button>}
      {!session ? <button type="button" className="secondary" disabled={action.busy || disabled} onClick={() => void connect()}>Start browser voice</button> : <>
        <button type="button" className="primary" disabled={action.busy || status !== "ready"} onClick={() => void command("listen")}>Speak question</button>
        <button type="button" className="primary" disabled={action.busy || status !== "listening"} onClick={() => void command("send")}>Send voice question</button>
        <button type="button" className="secondary" disabled={action.busy || status === "ready"} onClick={() => void command("interrupt")}>Stop playback or discard speech</button>
        <button type="button" className="secondary" disabled={action.busy} onClick={() => void command("close")}>End voice session</button>
      </>}
    </div>
    <ErrorNotice error={action.error} />
    {notice && <p role="alert">{notice}</p>}
    <div id={`voice-audio-${conversationId}`} />
    {!!events.length && <details><summary>Speech activity</summary><pre className="chat-json">{JSON.stringify(events, null, 2)}</pre></details>}
  </section>;
}
