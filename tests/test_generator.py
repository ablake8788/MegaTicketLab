from app.services.ticket_service import TicketService

def test_random_generation():
    tickets = TicketService().generate_tickets(10, "random")
    assert len(tickets) == 10
    for t in tickets:
        assert len(t.white_numbers) == 5
        assert len(set(t.white_numbers)) == 5
        assert all(1 <= n <= 70 for n in t.white_numbers)
        assert 1 <= t.mega_ball <= 24

def test_compare():
    tickets = TicketService().generate_tickets(2, "random")
    results = TicketService().compare(tickets, [1, 20, 30, 46, 68], 17)
    assert len(results) == 2
    assert all("white_matches" in r for r in results)
