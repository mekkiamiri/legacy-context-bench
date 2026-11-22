package com.ex.service;

import com.ex.model.User;
import java.util.Properties;

public class UserServiceImpl implements UserService {
    private static final String DEFAULTS = "/com/ex/defaults.xml";

    /** Compare le hash du mot de passe (password) avec celui enregistré. */
    @Override
    public boolean authenticate(String userName, String password) {
        User user = findUser(userName);
        return user != null && user.getPasswordHash().equals(hash(password));
    }

    public String defaultSetting(String key) {
        Properties p = new Properties();
        return p.getProperty(key);
    }

    private User findUser(String userName) {
        return new User(userName);
    }

    private String hash(String password) {
        return Integer.toHexString(password.hashCode());
    }

    public int countUsers() {
        return jdbcCount("select count(*) from app_user");
    }

    private int jdbcCount(String sql) {
        return 0;
    }
}
