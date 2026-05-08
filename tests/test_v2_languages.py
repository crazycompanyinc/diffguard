from diffguard.v2.languages import MultiLanguageAnalyzer


def test_multilanguage_analyzer_extracts_typescript_contracts():
    profile = MultiLanguageAnalyzer().analyze_path(
        "src/routes/users.ts",
        """
import express from "express";
export async function listUsers(req: Request): Promise<User[]> {
  return db.query("select * from users");
}
router.get("/users", listUsers);
""",
    )

    assert profile.language == "typescript"
    assert any(symbol.name == "listUsers" for symbol in profile.symbols)
    assert any(contract["name"] == "route_requires_auth" for contract in profile.contracts)
    assert "db" in profile.concerns


def test_multilanguage_analyzer_supports_go_java_ruby_and_rust():
    analyzer = MultiLanguageAnalyzer()

    samples = {
        "main.go": "func SaveUser(ctx context.Context, user User) error { return repo.Save(user) }",
        "UserService.java": "public class UserService { public User findUser(String id) { return repo.find(id); } }",
        "users.rb": "class UsersController\n def show\n  render json: User.find(params[:id])\n end\nend",
        "lib.rs": "pub fn load_user(id: String) -> Result<User, Error> { repo.load(id) }",
    }

    for path, text in samples.items():
        profile = analyzer.analyze_path(path, text)
        assert profile.language != "unknown"
        assert profile.symbols
