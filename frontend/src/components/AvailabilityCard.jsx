/**
 * AvailabilityCard — renders the structured availability result
 * returned by the backend when type === 'availability_result'.
 *
 * Only shows data the backend actually provides. Never invents prices,
 * images, or booking options.
 */

function RoomRow({ room }) {
  return (
    <div className="avail-room">
      <div className="avail-room-name">{room.room_type}</div>
      <div className="avail-room-meta">
        <span className="avail-pill">Up to {room.max_adults} guest{room.max_adults !== 1 ? 's' : ''}</span>
        <span className="avail-pill avail-pill--accent">
          {room.available_rooms} room{room.available_rooms !== 1 ? 's' : ''} available
        </span>
      </div>
    </div>
  )
}

export default function AvailabilityCard({ data }) {
  if (!data) return null

  const { check_in, check_out, adults, available, rooms = [] } = data

  return (
    <div className="avail-card">
      <div className="avail-meta-row">
        <span className="avail-meta-item">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
          {check_in} — {check_out}
        </span>
        <span className="avail-meta-item">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
          {adults} adult{adults !== 1 ? 's' : ''}
        </span>
      </div>

      {available && rooms.length > 0 ? (
        <div className="avail-rooms">
          {rooms.map((room, i) => <RoomRow key={i} room={room} />)}
        </div>
      ) : (
        <p className="avail-none">No rooms match your search. Try different dates or contact us directly.</p>
      )}
    </div>
  )
}
