package com.ddmo.app;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class CustomerArchiveAndProfileIT {

    private static final Path DB = Path.of("target", "show-it-" + UUID.randomUUID() + ".db").toAbsolutePath();

    @DynamicPropertySource
    static void dbProps(DynamicPropertyRegistry registry) throws Exception {
        Files.createDirectories(DB.getParent());
        registry.add("spring.datasource.url", () -> "jdbc:sqlite:" + DB);
    }

    @Autowired MockMvc mockMvc;
    @Autowired ObjectMapper om;

    String token;
    final String user = "itmgr_" + UUID.randomUUID().toString().replace("-", "").substring(0, 10);
    String phoneA;
    String phoneB;

    @BeforeEach
    void registerAndLogin() throws Exception {
        phoneA = "138" + String.format("%08d", Math.floorMod(UUID.randomUUID().hashCode(), 100_000_000));
        phoneB = "139" + String.format("%08d", Math.floorMod(UUID.randomUUID().hashCode(), 100_000_000));
        String reg = "{\"username\":\"" + user + "\",\"password\":\"Test1234!\",\"nickname\":\"IT\"}";
        mockMvc.perform(post("/api/auth/register").contentType(MediaType.APPLICATION_JSON).content(reg))
            .andExpect(status().isOk());
        String login = "{\"username\":\"" + user + "\",\"password\":\"Test1234!\"}";
        MvcResult res = mockMvc.perform(post("/api/auth/login").contentType(MediaType.APPLICATION_JSON).content(login))
            .andExpect(status().isOk()).andReturn();
        JsonNode body = om.readTree(res.getResponse().getContentAsString());
        token = body.path("data").path("token").asText(null);
        assertNotNull(token, "token missing: " + res.getResponse().getContentAsString());
    }

    private String auth() { return "Bearer " + token; }

    @Test
    void namePhoneUpdate_uniqueConstraint_archiveSoftDeleteIdempotent() throws Exception {
        String create = "{\"name\":\"MemberA\",\"phone\":\"" + phoneA + "\",\"remark\":\"it\"}";
        MvcResult created = mockMvc.perform(post("/api/customers").header("Authorization", auth())
                .contentType(MediaType.APPLICATION_JSON).content(create))
            .andExpect(status().isOk()).andReturn();
        String id = om.readTree(created.getResponse().getContentAsString()).path("data").path("id").asText();
        assertFalse(id.isBlank());

        String upd = "{\"name\":\"MemberA2\",\"phone\":\"" + phoneA + "\",\"remark\":\"it2\"}";
        MvcResult updated = mockMvc.perform(put("/api/customers/" + id).header("Authorization", auth())
                .contentType(MediaType.APPLICATION_JSON).content(upd))
            .andExpect(status().isOk()).andReturn();
        assertEquals("MemberA2", om.readTree(updated.getResponse().getContentAsString()).path("data").path("name").asText());

        mockMvc.perform(post("/api/customers").header("Authorization", auth())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"MemberB\",\"phone\":\"" + phoneB + "\"}"))
            .andExpect(status().isOk());

        // unique phone conflict
        MvcResult clash = mockMvc.perform(put("/api/customers/" + id).header("Authorization", auth())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"MemberA2\",\"phone\":\"" + phoneB + "\"}"))
            .andReturn();
        String clashBody = clash.getResponse().getContentAsString();
        assertTrue(clash.getResponse().getStatus() >= 400 || clashBody.contains("唯一") || clashBody.contains("\"success\":false"),
            clashBody);

        MvcResult arch = mockMvc.perform(post("/api/customers/" + id + "/archive").header("Authorization", auth()))
            .andExpect(status().isOk()).andReturn();
        JsonNode a = om.readTree(arch.getResponse().getContentAsString()).path("data");
        assertTrue(a.path("ledgerPreserved").asBoolean());
        assertFalse(a.path("permanentDelete").asBoolean());
        assertEquals("inactive", a.path("customer").path("status").asText());
        assertFalse(a.path("idempotent").asBoolean());

        MvcResult arch2 = mockMvc.perform(post("/api/customers/" + id + "/archive").header("Authorization", auth()))
            .andExpect(status().isOk()).andReturn();
        assertTrue(om.readTree(arch2.getResponse().getContentAsString()).path("data").path("idempotent").asBoolean());
    }

    @Test
    void unauthorizedArchiveRejected() throws Exception {
        mockMvc.perform(post("/api/customers/1/archive"))
            .andExpect(status().isUnauthorized());
    }
}
